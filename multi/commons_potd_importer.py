#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update page with Wikimedia Commons picture of the day

The following parameters are supported:

-always           Don't prompt to save changes.

&params;
"""
# Author : JJMC89
# License: MIT

import mwparserfromhell
from mwparserfromhell.nodes import Wikilink
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import MultipleSitesBot, ExistingPageBot

docuReplacements = { # pylint: disable=invalid-name
    '&params;': pagegenerators.parameterHelp
}


def get_template_titles(templates):
    """
    Given an iterable of templates, return a set of pages.

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
        titles.add(template.title(with_ns=template.namespace() != 10))
        for tpl in template.backlinks(filter_redirects=True):
            titles.add(tpl.title(with_ns=tpl.namespace() != 10))
    return titles


class CommonsPotdImporter(MultipleSitesBot, ExistingPageBot):
    """Bot to import the Commons POTD with caption."""

    def __init__(self, generator, **kwargs):
        """
        Iniitializer.

        @param generator: the page generator that determines on which pages
            to work
        @type generator: generator
        """
        self.generator = generator
        super().__init__(**kwargs)
        self.commons = pywikibot.Site('commons', 'commons')
        date = self.commons.server_time().date().isoformat()
        self.potd_title = 'Template:Potd/{}'.format(date)
        potd_tpl = pywikibot.Page(self.commons, self.potd_title)
        potd_fn_titles = get_template_titles([
            pywikibot.Page(self.commons, 'Template:Potd filename')])
        wikicode = mwparserfromhell.parse(potd_tpl.text, skip_style_tags=True)
        for tpl in wikicode.ifilter_templates():
            if (tpl.name.matches(potd_fn_titles)
                    and tpl.has('1', ignore_empty=True)):
                self.potd = tpl.get('1').value.strip()
                break
        else:
            raise ValueError('Failed to find the POTD.')
        self.potd_desc_titles = get_template_titles([
            pywikibot.Page(self.commons, 'Template:Potd description')])
        # T242081, T243701
        # repo = self.commons.data_repository
        # self.DOC_ITEM = pywikibot.ItemPage(repo, 'Q4608595')

    def treat_page(self):
        """Process one page."""
        site = self.current_page.site
        # doc_tpl = self.DOC_ITEM.getSitelink(site)
        doc_tpl = pywikibot.Page(site, 'Documentation', ns=10)
        summary = 'Updating Commons picture of the day, '
        caption = ''
        for lang in {site.lang, 'en'}:
            caption_title = '{} ({})'.format(self.potd_title, lang)
            caption_page = pywikibot.Page(self.commons, caption_title)
            if not caption_page.exists():
                continue
            wikicode = mwparserfromhell.parse(caption_page.text,
                                              skip_style_tags=True)
            for tpl in wikicode.ifilter_templates():
                if (tpl.name.matches(self.potd_desc_titles)
                        and tpl.has('1', ignore_empty=True)):
                    caption = tpl.get('1').value.strip()
            if caption:
                # Remove templates, etc.
                caption = self.commons.expand_text(caption)
                # Make all interwikilinks go through Commons.
                caption = mwparserfromhell.parse(caption, skip_style_tags=True)
                for wikilink in caption.ifilter(forcetype=Wikilink):
                    title = wikilink.title.strip()
                    prefix = ':c' + ('' if title.startswith(':') else ':')
                    wikilink.title = prefix + title
                summary += '[[:c:{}|caption attribution]]'.format(
                    caption_title)
                break
        if not caption:
            summary += 'failed to get a caption'
        text = (
            '<includeonly>{{{{#switch:{{{{{{1|}}}}}}\n'
            '|caption={caption}\n'
            '|#default={file}\n'
            '}}}}</includeonly><noinclude>{{{{{doc}}}}}</noinclude>'.format(
                caption=str(caption),
                file=self.potd,
                doc=doc_tpl.title(with_ns=False)
            )
        )
        self.put_current(text, summary=summary, minor=False)


def main(*args):
    """
    Process command line arguments and invoke bot.
    If args is an empty list, sys.argv is used.
    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    gen_factory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        if arg == '-always':
            options['always'] = True
    CommonsPotdImporter(gen_factory.getCombinedGenerator(), **options).run()


if __name__ == '__main__':
    main()
