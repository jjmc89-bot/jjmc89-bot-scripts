#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This scripts generates a tabular report of AFC decline counts.

The following arguments are required:

-page             The page to output the report to.
"""
# Author : JJMC89
# License: MIT
import re
from collections import OrderedDict
import mwparserfromhell
import pywikibot
from pywikibot.pagegenerators import CategorizedPageGenerator

BOT_START_END = re.compile(
    r'^(.*?<!--\s*bot start\s*-->).*?(<!--\s*bot end\s*-->.*)$',
    flags=re.S | re.I
)


def validate_options(options, site):
    """
    Validate the options and return bool.

    @param options: options to validate
    @type options: dict

    @rtype: bool
    """
    pywikibot.log('Options:')
    required_keys = ['page']
    has_keys = list()
    result = True
    for key, value in options.items():
        pywikibot.log('-{} = {}'.format(key, value))
        if key in required_keys:
            has_keys.append(key)
        if key == 'page':
            if not isinstance(value, str):
                pywikibot.log('Must be a string.')
                result = False
            options[key] = pywikibot.Page(site, value)
        pywikibot.log('\u2192{} = {}'.format(key, options[key]))
    if sorted(has_keys) != sorted(required_keys):
        pywikibot.log('Missing one more required keys.')
        result = False
    return result


def save_bot_start_end(save_text, page, summary):
    """
    Writes the text to the given page.

    @param save_text: Text to save
    @type save_text: str
    @param page: Page to save to
    @type page: L{pywikibot.Page}
    @param summary: Edit summary
    @type summary: str
    """
    save_text = save_text.strip()
    if page.exists():
        if BOT_START_END.match(page.text):
            page.text = BOT_START_END.sub(r'\1\n{}\2'.format(save_text),
                                          page.text)
        else:
            page.text = save_text
        page.save(summary=summary, minor=False, botflag=False)
    else:
        pywikibot.error('{} does not exist. Skipping.'.format(page.title()))


def get_template_titles(templates):
    """
    Given an iterable of templates, return a set of titles.

    @param templates: iterable of templates (L{pywikibot.Page})
    @type templates: iterable

    @rtype: set
    """
    titles = set()
    for template in templates:
        if template.isRedirectPage():
            template = template.getRedirectTarget()
        if not template.exists():
            continue
        titles.add(template.title(withNamespace=False))
        titles.add(template.title(underscore=True, withNamespace=False))
        for tpl in template.backlinks(
                filterRedirects=True,
                namespaces=template.site.namespaces.TEMPLATE
        ):
            titles.add(tpl.title(withNamespace=False))
            titles.add(tpl.title(underscore=True, withNamespace=False))
    return titles


def output_afc_decline_counts(page=None):
    """
    Writes AFC decline countss to a page.

    @param page: The page to output to
    @type page: L{pywikibot.Page}
    """
    text = ''
    afc_tpl = pywikibot.Page(page.site, 'Template:AFC submission')
    afc_tpl_titles = get_template_titles([afc_tpl])
    afc_cat = pywikibot.Category(page.site, 'Declined AfC submissions')
    storage = dict()
    for afc_page in CategorizedPageGenerator(afc_cat, recurse=True,
                                             content=True):
        if afc_page in storage:
            continue
        declines = 0
        wikicode = mwparserfromhell.parse(afc_page.get(get_redirect=True),
                                          skip_style_tags=True)
        for tpl in wikicode.ifilter_templates():
            if not tpl.name.matches(afc_tpl_titles):
                continue
            for param in tpl.params:
                if (param.name.matches('1')
                        and param.value.strip().upper() == 'D'):
                    declines += 1
                    break
        storage[afc_page] = declines
    # Sort by declines then page
    storage = OrderedDict(sorted(storage.items(),
                                 key=lambda kv: (-kv[1], kv[0])))
    for afc_page, declines in storage.items():
        text += (
            '\n|-\n| {page} || {declines}'
            .format(
                page=afc_page.title(asLink=True, textlink=True),
                declines=declines if declines > 0 else 'Unknown',
            )
        )
    if text:
        text = (
            '\n{{| class="wikitable sortable"\n|+ Last updated: ~~~~~'
            '\n! Page !! Declines{body}\n|}}'
            .format(body=text)
        )
    else:
        text = 'None'
    save_bot_start_end(
        text,
        page,
        'Updating AfC decline counts report'
    )


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    for arg in local_args:
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg in 'page':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for {}'.format(arg),
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if not validate_options(options, site):
        pywikibot.error('Invalid options.')
        return False
    output_afc_decline_counts(page=options['page'])
    return True


if __name__ == "__main__":
    main()
