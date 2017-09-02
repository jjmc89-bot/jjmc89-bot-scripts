#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script generates BSicon reports.

    - Output changes to BSicons
    - List BSicon redirects
    - List large BSicons

The following parameters are required:

-config           The page title that has the JSON config (object).
                  Options set in the config override those provided when
                  running this script.

The following parameters are supported:

-changes_date     The table of changes is added for this date. The default
                  is yesterday.

-changes_summary  Edit summary to use when updating the file changes table

-changes_page_prefix Title prefix of the page to save the file changes

-redirects_page   Title of the page to save the redirects list

-list_summary     Edit summary to use when updating one the lists

-large_size       Files over this size will be included in the large files
                  list

-large_page       Title of the page to save the large files list
"""
# Author : JJMC89
# License: MIT
import datetime
from datetime import date, time, timedelta
import json
import os
import re
import sys
import pywikibot
from pywikibot import pagegenerators

BOT_START_END = re.compile(
    r'^(.*?<!--\s*bot start\s*-->).*?(<!--\s*bot end\s*-->.*)$',
    flags=re.S | re.I
)


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict or None
    """
    if not page.exists():
        pywikibot.error('%s does not exist.' % page.title())
        return
    elif page.isRedirectPage():
        pywikibot.error('%s is a redirect.' % page.title())
        return
    elif page.isEmpty():
        pywikibot.log('%s is empty.' % page.title())
        return
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error('%s does not contain valid JSON.' % page.title())
        raise


def get_page_from_size(page, size=1e6):
    """Return a page based on the current page size."""
    i = 1
    title = page.title()
    while True:
        if not page.exists():
            break
        if len(page.text) < size:
            break
        i += 1
        page = pywikibot.Page(
            page.site,
            '{} ({:02d})'.format(title, i)
        )
    return page


def validate_options(options, site):
    """
    Validate the options and return bool.

    @param options: options to validate
    @type options: dict

    @rtype: bool
    """
    pywikibot.log('Options:')
    required_keys = ['changes_date', 'changes_summary', 'changes_page_prefix',
                     'enabled', 'list_summary', 'large_page', 'large_size',
                     'redirects_page', 'logs_page_prefix', 'logs_summary']
    has_keys = list()
    if 'changes_date' in options:
        value = options['changes_date']
        if isinstance(value, datetime.date):
            pass
        elif isinstance(value, str):
            try:
                value = datetime.datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                pywikibot.error('Date format must be YYYY-MM-DD.')
                return False
        else:
            return False
        options['changes_date'] = value
    else:
        return False
    for key, value in options.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in required_keys:
            has_keys.append(key)
        if key == 'changes_date':
            pass
        elif key in ('changes_summary', 'list_summary', 'logs_page_prefix',
                     'logs_summary'):
            if not isinstance(value, str):
                return False
        elif key == 'changes_page_prefix':
            if not isinstance(value, str):
                return False
            changes_page = pywikibot.Page(
                site,
                '%s/%s' % (value, options['changes_date'].strftime('%Y-%m'))
            )
            changes_page = get_page_from_size(changes_page)
        elif key == 'enabled':
            if not isinstance(value, bool):
                return False
            elif value is not True:
                sys.exit('Task disabled.')
        elif key in 'large_page' 'redirects_page':
            if not isinstance(value, str):
                return False
            options[key] = pywikibot.Page(site, value)
        elif key == 'large_size':
            try:
                options[key] = int(value)
            except ValueError:
                return False
        else:
            return False
    if sorted(has_keys) != sorted(required_keys):
        return False
    options['changes_page'] = changes_page
    return True


def page_is_bsicon(page):
    """
    Returns whether the page is a BSicon.

    @param page: The page
    @type page: L{pywikibot.Page}

    @rtype: bool
    """
    if page.namespace() != page.site.namespaces.FILE:
        return False
    if not page.title(underscore=True,
                      withNamespace=False).startswith('BSicon_'):
        return False
    return True


def get_bsicon_name(file):
    """
    Return the BSicon name.

    @param file: The file
    @type file: L{pywikibot.FilePage}

    @rtype: str
    """
    return os.path.splitext(os.path.basename(file.title(
        withNamespace=False)))[0][7:]


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
            page.text = BOT_START_END.sub(r'\1\n%s\2' % save_text, page.text)
        else:
            page.text = save_text
        page.save(summary='BSicons: %s' % summary, minor=False)
    else:
        pywikibot.error('%s does not exist. Skipping.' % page.title())


def save_list(page_list, page, summary):
    """
    Writes the given page_list to the given page.

    @param page_list: List of pages to output
    @type page_list: list of L{pywikibot.Page}
    @param page: Page to save to
    @type page: L{pywikibot.Page}
    @param summary: Edit summary
    @type summary: str
    """
    list_text = ''
    for item in sorted(page_list):
        list_text += '\n# %s' % item.title(asLink=True, textlink=True)
    save_bot_start_end(list_text, page, summary)


def output_log(logtype=None, start=None, end=None, site=None, options=None,
               bsicon_template_title='bsq2'):
    """
    Writes logevents to a page.

    @param logtype: The logtype to output
    @type logtype: str
    @param site: The site being worked on
    @type site: L{pywikibot.Site}
    @param options: Validated options
    @type options: dict
    @param bsicon_template_title: Title of BSicon template to use
    @type bsicon_template_title: str
    """
    if not site:
        site = pywikibot.Site()
    log_text = ''
    log_page = pywikibot.Page(
        site,
        '%s/%s/%s' % (options['logs_page_prefix'], logtype,
                      options['changes_date'].strftime('%Y-%m'))
    )
    log_page = get_page_from_size(log_page)
    for logevent in site.logevents(logtype=logtype,
                                   namespace=site.namespaces.FILE.id,
                                   start=start, end=end, reverse=True):
        if not page_is_bsicon(logevent.page()):
            continue
        log_text += ('\n|-\n| {{%s|%s}}' % (bsicon_template_title,
                                            get_bsicon_name(logevent.page())))
        log_text += (
            ' || {r[logid]} || {r[timestamp]} || {r[user]} || '
            '<nowiki>{r[comment]}</nowiki>'.format(r=logevent.data)
        )
    if log_text:
        log_text = (
            '\n\n== %s =='
            '\n{| class="wikitable sortable mw-collapsible mw-collapsed"'
            '\n! BSicon !! logid !! Date/time !! User !! Summary'
            '%s\n|}' % (options['changes_date'].isoformat(), log_text)
        )
    else:
        log_text = ('\n\n== %s ==\n: None' %
                    options['changes_date'].isoformat())
    if log_page.exists():
        log_page.text += log_text
    else:
        log_page.text = ('{{%s}}%s' %
                         (options['logs_page_prefix'], log_text))
    log_page.save(
        minor=False,
        summary='/* %s */ BSicons: %s' %
        (options['changes_date'].isoformat(), options['logs_summary'])
    )


def output_move_log(start=None, end=None, site=None, options=None):
    """
    Writes move logevents to a page.

    @param site: The site being worked on
    @type site: L{pywikibot.Site}
    @param options: Validated options
    @type options: dict
    """
    if not site:
        site = pywikibot.Site()
    log_text = ''
    log_page = pywikibot.Page(
        site,
        '%s/%s/%s' % (options['logs_page_prefix'], 'move',
                      options['changes_date'].strftime('%Y-%m'))
    )
    log_page = get_page_from_size(log_page)
    for logevent in site.logevents(logtype='move',
                                   namespace=site.namespaces.FILE.id,
                                   start=start, end=end, reverse=True):
        is_bsicon = page_is_bsicon(logevent.page())
        target_is_bsicon = page_is_bsicon(logevent.target_page)
        if not (is_bsicon or target_is_bsicon):
            continue
        log_text += '\n|-\n| '
        if is_bsicon:
            log_text += '{{bsn|%s}}' % get_bsicon_name(logevent.page())
        else:
            log_text += logevent.page().title(asLink=True, textlink=True)
        log_text += ' || '
        if target_is_bsicon:
            log_text += '{{bsq2|%s}}' % get_bsicon_name(logevent.target_page)
        else:
            log_text += logevent.target_page.title(asLink=True, textlink=True)
        log_text += (
            ' || {r[logid]} || {r[timestamp]} || {r[user]} || '
            '<nowiki>{r[comment]}</nowiki>'.format(r=logevent.data)
        )
    if log_text:
        log_text = (
            '\n\n== %s =='
            '\n{| class="wikitable sortable mw-collapsible mw-collapsed"'
            '\n! Page !! Target !! logid !! Date/time !! User !! Summary'
            '%s\n|}' % (options['changes_date'].isoformat(), log_text)
        )
    else:
        log_text = ('\n\n== %s ==\n: None' %
                    options['changes_date'].isoformat())
    if log_page.exists():
        log_page.text += log_text
    else:
        log_page.text = ('{{%s}}%s' %
                         (options['logs_page_prefix'], log_text))
    log_page.save(
        minor=False,
        summary='/* %s */ BSicons: %s' %
        (options['changes_date'].isoformat(), options['logs_summary'])
    )


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'enabled': False,
        'changes_date': date.today() - timedelta(days=1),
        'changes_summary': 'Updating changes',
        'large_size': 1000,
        'list_summary': 'Updating list',
        'logs_summary': 'Updating log'
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    gen_factory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg in ('config', 'changes_date', 'changes_summary',
                   'changes _page_prefix', 'redirects_page', 'large_size',
                   'large_page', 'list_summary', 'logs_page_prefix',
                   'logs_summary'):
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if 'config' in options:
        config = pywikibot.Page(site, options.pop('config'))
        config = get_json_from_page(config)
        options.update(config)
    else:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    if not validate_options(options, site):
        pywikibot.error('Invalid options.')
        return False

    start = datetime.datetime.combine(options['changes_date'], time.min)
    end = datetime.datetime.combine(options['changes_date'], time.max)

    # Output logs
    output_log(logtype='upload', start=start, end=end, site=site,
               options=options)
    output_log(logtype='delete', start=start, end=end, site=site,
               options=options, bsicon_template_title='bsn')
    output_move_log(start=start, end=end, site=site, options=options)

    # Build changes table and lists of files
    file_changes = ''
    file_redirects = set()
    large_files = set()
    for file in pagegenerators.PrefixingPageGenerator('File:BSicon_'):
        if not (file.exists() and page_is_bsicon(file)):
            continue
        for rev in file.revisions(starttime=start, endtime=end, reverse=True):
            file_changes += '\n|-\n| {{bsq2|%s}}' % get_bsicon_name(file)
            file_changes += (
                ' || {r.revid} || {r.timestamp} || {r.user} || '
                '<nowiki>{r.comment}</nowiki>'.format(r=rev.hist_entry())
            )
        if file.isRedirectPage():
            file_redirects.add(file)
        else:
            try:
                size = file.site.loadimageinfo(file)['size']
                if size > options['large_size']:
                    large_files.add(file)
            except (ValueError, pywikibot.PageRelatedError) as e:
                pywikibot.exception(e, tb=True)
    if file_changes:
        file_changes = (
            '\n\n== %s =='
            '\n{| class="wikitable sortable mw-collapsible mw-collapsed"'
            '\n! BSicon !! revid !! Date/time !! User !! Summary'
            '%s\n|}' % (options['changes_date'].isoformat(), file_changes)
        )
    else:
        file_changes = ('\n\n== %s ==\n: No changes' %
                        options['changes_date'].isoformat())
    if options['changes_page'].exists():
        options['changes_page'].text += file_changes
    else:
        options['changes_page'].text = ('{{%s}}%s' %
                                        (options['changes_page_prefix'],
                                         file_changes))
    options['changes_page'].save(
        minor=False,
        summary='/* %s */ BSicons: %s' %
        (options['changes_date'].isoformat(), options['changes_summary'])
    )
    save_list(file_redirects, options['redirects_page'],
              summary=options['list_summary'])
    save_list(large_files, options['large_page'],
              summary=options['list_summary'])


if __name__ == "__main__":
    main()
