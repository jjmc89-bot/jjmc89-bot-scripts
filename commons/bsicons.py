#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : BSicons:
         - Output changes to BSicons
         - List BSicon redirects
         - List large BSicons
Author : JJMC89

The following parameters are required:

-config           The page title that has the JSON config (object).
                  Options set in the config override those provided when
                  running this script.

The following parameters are supported:

-changesDate      The table of changes is added for this date. The default
                  is yesterday.

-changesSummary   Edit summary to use when updating the file changes table

-changesPagePrefix Title prefix of the page to save the file changes

-redirectsPage    Title of the page to save the redirects list

-listSummary      Edit summary to use when updating one the lists

-largeSize        Files over this size will be included in the large files
                  list

-largePage        Title of the page to save the large files list
"""
import datetime
from datetime import date, time, timedelta
import json
import os
import re
import sys
import pywikibot
from pywikibot import pagegenerators

__version__ = '$Id$'

BOTSTARTEND = re.compile(
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
    requiredKeys = [
        'changesDate',
        'changesSummary',
        'changesPagePrefix',
        'enabled',
        'listSummary',
        'largePage',
        'largeSize',
        'redirectsPage',
        'logsPagePrefix',
        'logsSummary'
    ]
    hasKeys = []
    if 'changesDate' in options:
        value = options['changesDate']
        if isinstance(value, datetime.date):
            pass
        elif isinstance(value, str):
            try:
                value = datetime.datetime.strptime(value, '%Y-%m-%d').date()
            except:
                pywikibot.error('Date format must be YYYY-MM-DD.')
                return False
        else:
            return False
        options['changesDate'] = value
    else:
        return False
    for key, value in options.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in requiredKeys:
            hasKeys.append(key)
        if key == 'changesDate':
            pass
        elif key in (
            'changesSummary',
            'listSummary',
            'logsPagePrefix',
            'logsSummary'
        ):
            if not isinstance(value, str):
                return False
        elif key == 'changesPagePrefix':
            if not isinstance(value, str):
                return False
            fileChangesPage = pywikibot.Page(
                site,
                '%s/%s' % (value, options['changesDate'].strftime('%Y-%m'))
            )
        elif key == 'enabled':
            if not isinstance(value, bool):
                return False
            elif value is not True:
                sys.exit('Task disabled.')
        elif key in (
            'largePage',
            'redirectsPage'
        ):
            if not isinstance(value, str):
                return False
            options[key] = pywikibot.Page(site, value)
        elif key == 'largeSize':
            try:
                options[key] = int(value)
            except:
                return False
        else:
            return False
    if sorted(hasKeys) != sorted(requiredKeys):
        return False
    options['fileChangesPage'] = fileChangesPage
    return True


def page_is_BSicon(page):
    """
    Returns whether the page is a BSicon

    @param page: The page
    @type page: L{pywikibot.Page}

    @rtype: bool
    """
    try:
        file = pywikibot.FilePage(page)
    except:
        return False
    title = file.title(underscore=True, withNamespace=False)
    if not title.startswith('BSicon_'):
        return False
    return True


def get_BSicon_name(file):
    """
    Return the BSicon name.

    @param file: The file
    @type file: L{pywikibot.FilePage}

    @rtype: str
    """
    title = file.title(withNamespace=False)
    return os.path.splitext(os.path.basename(title))[0][7:]


def save_botstartend(savetext, page, summary):
    """
    Writes the text to the given page.

    @param savetext: Text to save
    @type savetext: str
    @param page: Page to save to
    @type page: L{pywikibot.Page}
    @param summary: Edit summary
    @type summary: str
    """
    savetext = savetext.strip()
    if page.exists():
        text = page.get().strip()
        if BOTSTARTEND.match(text):
            newtext = BOTSTARTEND.sub(r'\1\n%s\2' % savetext, text)
        else:
            newtext = savetext
        if newtext != text:
            page.text = newtext
            page.save(summary='BSicons: %s' % summary, minor=False)
    else:
        pywikibot.error('%s does not exist. Skipping.' % page.title())


def save_list(list, page, summary):
    """
    Writes the given list to the given page.

    @param list: List of pages to output
    @type list: list of L{pywikibot.Page}
    @param page: Page to save to
    @type page: L{pywikibot.Page}
    @param summary: Edit summary
    @type summary: str
    """
    listtext = ''
    for item in sorted(list):
        listtext += '\n# %s' % item.title(asLink=True, textlink=True)
    save_botstartend(listtext, page, summary)


def output_log(logtype=None, start=None, end=None, site=None, options=dict(),
               BSiconTemplateTitle='bsq'):
    """
    Writes logevents to a page.

    @param logtype: The logtype to output
    @type logtype: str
    @param site: The site being worked on
    @type site: L{pywikibot.Site}
    @param options: Validated options
    @type options: dict
    @param BSiconTemplate: Title of BSicon template to use
    @type BSiconTemplate: str
    """
    if not site:
        site = pywikibot.Site()
    logText = ''
    logPage = pywikibot.Page(
        site,
        '%s/%s/%s' % (options['logsPagePrefix'], logtype,
                      options['changesDate'].strftime('%Y-%m'))
    )
    for logevent in site.logevents(logtype=logtype,
                                   namespace=site.namespaces.FILE.id,
                                   start=start, end=end, reverse=True):
        file = logevent.page()
        if not page_is_BSicon(file):
            continue
        logText += ('\n|-\n| {{%s|%s}}' % (BSiconTemplateTitle,
                                           get_BSicon_name(file)))
        logText += (
            ' || {r[logid]} || {r[timestamp]} || {r[user]} || '
            '<nowiki>{r[comment]}</nowiki>'.format(r=logevent.data)
        )
    if logText:
        logText = (
            '\n\n== %s =='
            '\n{| class="wikitable sortable mw-collapsible mw-collapsed"'
            '\n! BSicon !! logid !! Date/time !! User !! Summary'
            '%s\n|}' % (options['changesDate'].isoformat(), logText)
        )
    else:
        logText = ('\n\n== %s ==\n: None' %
                   options['changesDate'].isoformat())
    if logPage.exists():
        logPage.text += logText
    else:
        logPage.text = ('{{%s}}%s' %
                        (options['logsPagePrefix'], logText))
    logPage.save(
        minor=False,
        summary='/* %s */ BSicons: %s' %
        (options['changesDate'].isoformat(), options['logsSummary'])
    )


def output_move_log(start=None, end=None, site=None, options=dict()):
    """
    Writes move logevents to a page.

    @param site: The site being worked on
    @type site: L{pywikibot.Site}
    @param options: Validated options
    @type options: dict
    """
    if not site:
        site = pywikibot.Site()
    logText = ''
    logPage = pywikibot.Page(
        site,
        '%s/%s/%s' % (options['logsPagePrefix'], 'move',
                      options['changesDate'].strftime('%Y-%m'))
    )
    for logevent in site.logevents(logtype='move',
                                   namespace=site.namespaces.FILE.id,
                                   start=start, end=end, reverse=True):
        file = logevent.page()
        isBSicon = page_is_BSicon(file)
        targetPage = logevent.target_page
        targetIsBSicon = page_is_BSicon(targetPage)
        if not (isBSicon or targetIsBSicon):
            continue
        logText += '\n|-\n| '
        if isBSicon:
            logText += '{{bsn|%s}}' % get_BSicon_name(file)
        else:
            logText += file.title(asLink=True, textlink=True)
        logText += ' || '
        if targetIsBSicon:
            logText += '{{bsq|%s}}' % get_BSicon_name(targetPage)
        else:
            logText += targetPage.title(asLink=True, textlink=True)
        logText += (
            ' || {r[logid]} || {r[timestamp]} || {r[user]} || '
            '<nowiki>{r[comment]}</nowiki>'.format(r=logevent.data)
        )
    if logText:
        logText = (
            '\n\n== %s =='
            '\n{| class="wikitable sortable mw-collapsible mw-collapsed"'
            '\n! Page !! Target !! logid !! Date/time !! User !! Summary'
            '%s\n|}' % (options['changesDate'].isoformat(), logText)
        )
    else:
        logText = ('\n\n== %s ==\n: None' %
                   options['changesDate'].isoformat())
    if logPage.exists():
        logPage.text += logText
    else:
        logPage.text = ('{{%s}}%s' %
                        (options['logsPagePrefix'], logText))
    logPage.save(
        minor=False,
        summary='/* %s */ BSicons: %s' %
        (options['changesDate'].isoformat(), options['logsSummary'])
    )


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'enabled': False,
        'changesDate': date.today() - timedelta(days=1),
        'changesSummary': 'Updating changes',
        'largeSize': 1000,
        'listSummary': 'Updating list',
        'logsSummary': 'Updating log'
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    genFactory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        arg, sep, value = arg.partition(':')
        option = arg[1:]
        if option in (
            'config',
            'changesDate',
            'changesSummary',
            'changesPagePrefix',
            'redirectsPage',
            'largeSize',
            'largePage',
            'listSummary',
            'logsPagePrefix',
            'logsSummary'
        ):
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[option] = value
        else:
            options[option] = True
    if 'config' in options:
        config = pywikibot.Page(site, options.pop('config'))
        if config.exists():
            config = config.get().strip()
            try:
                config = json.loads(config)
            except:
                raise
            else:
                if isinstance(config, dict):
                    options.update(config)
                else:
                    pywikibot.error('Invalid config format.')
        else:
            pywikibot.error('%s does not exist.' % config.title())
            return False
    else:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    if not validate_options(options, site):
        pywikibot.error('Invalid options.')
        return False

    start = datetime.datetime.combine(options['changesDate'], time.min)
    end = datetime.datetime.combine(options['changesDate'], time.max)

    # Output logs
    output_log(logtype='upload', start=start, end=end, site=site,
               options=options)
    output_log(logtype='delete', start=start, end=end, site=site,
               options=options, BSiconTemplateTitle='bsn')
    output_move_log(start=start, end=end, site=site, options=options)

    # Build changes table and lists of files
    fileChanges = ''
    fileChangesPage = options['fileChangesPage']
    fileRedirects = []
    largeFiles = []
    BSicons = pagegenerators.PrefixingPageGenerator('File:BSicon_')
    for file in BSicons:
        if not (file.exists() and page_is_BSicon(file)):
            continue
        for rev in file.revisions(
            starttime=start,
            endtime=end,
            reverse=True
        ):
            fileChanges += '\n|-\n| {{bsq|%s}}' % get_BSicon_name(file)
            fileChanges += (
                ' || {r.revid} || {r.timestamp} || {r.user} || '
                '<nowiki>{r.comment}</nowiki>'.format(r=rev.hist_entry())
            )
        if file.isRedirectPage():
            fileRedirects.append(file)
        else:
            try:
                size = file.site.loadimageinfo(file)['size']
                if size > options['largeSize']:
                    largeFiles.append(file)
            except Exception as e:
                pywikibot.exception(e, tb=True)
    if fileChanges:
        fileChanges = (
            '\n\n== %s =='
            '\n{| class="wikitable sortable mw-collapsible mw-collapsed"'
            '\n! BSicon !! revid !! Date/time !! User !! Summary'
            '%s\n|}' % (options['changesDate'].isoformat(), fileChanges)
        )
    else:
        fileChanges = ('\n\n== %s ==\n: No changes' %
                       options['changesDate'].isoformat())
    if fileChangesPage.exists():
        fileChangesPage.text += fileChanges
    else:
        fileChangesPage.text = ('{{%s}}%s' %
                                (options['changesPagePrefix'], fileChanges))
    fileChangesPage.save(
        minor=False,
        summary='/* %s */ BSicons: %s' %
        (options['changesDate'].isoformat(), options['changesSummary'])
    )
    save_list(fileRedirects, options['redirectsPage'],
              summary=options['listSummary'])
    save_list(largeFiles, options['largePage'],
              summary=options['listSummary'])


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
