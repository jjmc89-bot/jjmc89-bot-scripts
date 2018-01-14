#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This scripts generates a tabular report of draftifications over a specified
date range.

The following arguments are required:

-page             The page to output the report to.

The following arguments are supported:

-end              The end date of the range for the report.
                  If -end is not provided, it will be yesterday.

-start            The start date of the range for the report.
                  If -start is not provided, it will be the same as -end.
"""
# Author : JJMC89
# License: MIT
import datetime
from datetime import date, timedelta
import re
from dateutil.parser import parse as parse_date
import pywikibot
from pywikibot import pagegenerators

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
    required_keys = ['end', 'page', 'start']
    has_keys = list()
    result = True
    if 'start' not in options:
        options['start'] = options['end']
    for key, value in options.items():
        pywikibot.log('-{} = {}'.format(key, value))
        if key in required_keys:
            has_keys.append(key)
        if key in 'end' 'start':
            if not isinstance(value, date):
                try:
                    options[key] = parse_date(value).date()
                except ValueError as e:
                    pywikibot.log('Invalid date: {}'.format(e))
                    result = False
        elif key == 'page':
            if not isinstance(value, str):
                pywikibot.log('Must be a string.')
                result = False
            options[key] = pywikibot.Page(site, value)
        pywikibot.log('\u2192{} = {}'.format(key, options[key]))
    if sorted(has_keys) != sorted(required_keys):
        pywikibot.log('Missing one more required keys.')
        result = False
    if options['end'] < options['start']:
        pywikibot.log('end cannot be before start.')
        result = False
    return result


def get_xfds(pages):
    """
    Return a set of XfDs for the pages.

    @param pages: Pages to get XfDs for
    @type pages: iterable of L{pywikibot.Page}

    @rtype: set
    """
    xfds = set()
    for page in pages:
        if page.namespace() == page.site.namespaces.MAIN:
            prefix = 'Articles for deletion/'
        else:
            prefix = 'Miscellany for deletion/'
        prefix += page.title()
        gen = pagegenerators.PrefixingPageGenerator(
            prefix, namespace=page.site.namespaces.PROJECT, site=page.site)
        xfds = xfds.union([xfd_page.title(asLink=True) for xfd_page in gen])
    return xfds


def iterable_to_wikitext(items):
    """
    Convert iterable to wikitext.

    @param items: Items to iterate
    @type items: iterable

    @rtype: str
    """
    if len(items) == 1:
        return '{}'.format(next(iter(items)))
    text = ''
    for item in items:
        text += '\n* {}'.format(item)
    return text


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


def output_move_log(page=None, start=None, end=None):
    """
    Writes move logevents to a page.

    @param page: The page to output to
    @type page: L{pywikibot.Page}
    """
    text = ''
    for logevent in page.site.logevents(logtype='move',
                                        namespace=page.site.namespaces.MAIN.id,
                                        start=start, end=end, reverse=True):
        if (logevent.target_ns not in (page.site.namespaces.DRAFT,
                                       page.site.namespaces.USER)
                or logevent.target_title.startswith('Draft:Move/')):
            # Only want moves to Draft or User.
            # Skip page swaps.
            continue
        current_page = None
        creator = creation = last_edit = num_editors = '(Unknown)'
        if logevent.target_page.exists():
            current_page = logevent.target_page
            if current_page.isRedirectPage():
                try:
                    redirect_target = current_page.getRedirectTarget()
                except pywikibot.CircularRedirect:
                    pywikibot.log('{} is a circular redirect.'.format(
                        current_page.title(asLink=True)))
                else:
                    if (redirect_target.exists()
                            and (redirect_target.namespace()
                                 in (page.site.namespaces.DRAFT,
                                     page.site.namespaces.USER,
                                     page.site.namespaces.MAIN))
                       ):
                        current_page = redirect_target
        elif logevent.page().exists():
            current_page = logevent.page()
        if current_page:
            if current_page.oldest_revision.user:
                creator = '[[User:{}]]'.format(
                    current_page.oldest_revision.user)
            creation = ('[[Special:PermaLink/{rev.revid}|{rev.timestamp}]]'
                        .format(rev=current_page.oldest_revision))
            last_edit = '[[Special:Diff/{rev.revid}|{rev.timestamp}]]'.format(
                rev=current_page.latest_revision)
            editors = set()
            for rev in current_page.revisions():
                if rev.user:
                    editors.add(rev.user)
            num_editors = len(editors)
        text += (
            '\n|-\n| {page} || {target} || [[User:{log[user]}]] || '
            '{log[timestamp]} || <nowiki>{log[comment]}</nowiki> || '
            '{creator} || {creation} || {editors} || {last_edit} || {notes}'
            .format(
                page=logevent.page().title(asLink=True, textlink=True),
                target=logevent.target_page.title(asLink=True, textlink=True),
                log=logevent.data,
                creator=creator,
                creation=creation,
                editors=num_editors,
                last_edit=last_edit,
                notes=iterable_to_wikitext(
                    get_xfds([logevent.page(), logevent.target_page])
                )
            )
        )
    if text:
        if start.date() == end.date():
            caption = 'Report for {}'.format(start.date().isoformat())
        else:
            caption = 'Report for {} to {}'.format(start.date().isoformat(),
                                                   end.date().isoformat())
        caption += '; Last updated: ~~~~~'
        text = (
            '\n{{| class="wikitable sortable plainlinks"\n|+ {caption}'
            '\n! Page !! Target !! Mover !! Move date/time !! Move summary !! '
            'Creator !! Creation !! Editors !! Last edit !! Notes{body}\n|}}'
            .format(caption=caption, body=text)
        )
    else:
        text = 'None'
    save_bot_start_end(text, page, 'Updating draftification report')


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'end': date.today() - timedelta(days=1)
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    for arg in local_args:
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg in 'end' 'page' 'start':
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

    # Output logs
    output_move_log(
        page=options['page'],
        start=datetime.datetime.combine(options['start'], datetime.time.min),
        end=datetime.datetime.combine(options['end'], datetime.time.max)
    )
    return True


if __name__ == "__main__":
    main()
