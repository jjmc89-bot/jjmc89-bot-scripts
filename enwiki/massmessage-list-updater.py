#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : User groups MassMessage list updater
Author : JJMC89


The following parameters are required:

-config           The page title that has the JSON config (object)

The following parameters are supported:

-endDate          Logs will be parsed starting on this date. The default is
                  yesterday. Format: YYYY-MM-DD.

-meta             metawiki will also be checked for group changes. Should be
                  specified when running on WMF wikis with CentralAuth.

-rename           Rename logs will be parsed. If -meta from metawiki.

-startDate        Logs will be parsed ending on this date. The default is
                  yesterday. Format: YYYY-MM-DD.
"""
from collections import OrderedDict
import datetime
from datetime import date, time, timedelta
from itertools import chain
import json
from operator import itemgetter
import re
import sys
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot

__version__ = '$Id$'


def validate_config(config, site):
    """
    Validate the configuration and return bool.

    @param config: configuration to validate
    @type config: dict
    @param site: site used in the validation
    @type site: L{pywikibot.Site}

    @rtype: bool
    """
    pywikibot.log('config:')
    if not isinstance(config, dict):
        return False
    for title, pageConfig in config.items():
        pywikibot.log('-%s: %s' % (title, pageConfig))
        pageConfig['page'] = pywikibot.Page(site, title)
        requiredKeys = [
            'enabled',
            'group',
            'page'
        ]
        hasKeys = []
        for key, value in pageConfig.items():
            if key in requiredKeys:
                hasKeys.append(key)
            if key in ('add', 'enabled', 'remove', 'required'):
                if not isinstance(value, bool):
                    return False
            elif key == 'group':
                if isinstance(value, str):
                    pageConfig[key] = set([value])
                else:
                    return False
            elif key == 'page':
                if value.content_model != 'MassMessageListContent':
                    return False
            else:
                return False
        if sorted(hasKeys) != sorted(requiredKeys):
            return False
    return True


def validate_options(options, site):
    """
    Validate the options and return bool.

    @param options: options to validate
    @type options: dict
    @param site: site used in the validation
    @type site: L{pywikibot.Site}

    @rtype: bool
    """
    pywikibot.log('Options:')
    requiredKeys = [
        'config',
        'endDate',
        'startDate'
    ]
    hasKeys = []
    for key in ('endDate', 'startDate'):
        if key not in options:
            continue
        value = options[key]
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
        options[key] = value
    for key, value in options.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in requiredKeys:
            hasKeys.append(key)
        if key == 'config':
            if not isinstance(value, str):
                return False
        elif key in ('endDate', 'startDate'):
            if not isinstance(value, datetime.date):
                return False
    if sorted(hasKeys) != sorted(requiredKeys):
        return False
    return True


class UserGroupsMassMessageListUpdater(
    SingleSiteBot,
    ExistingPageBot,
    NoRedirectPageBot
):

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'config': dict(),
            'groupChanges': list(),
            'renames': [{
                'olduser': None,
                'newuser': None,
                'timestamp': None
            }]
        })

        self.generator = generator
        super(UserGroupsMassMessageListUpdater, self).__init__(**kwargs)

        self.config = self.getOption('config')
        self.groupChanges = self.getOption('groupChanges')
        self.renames = self.getOption('renames')
        self.checkEnabledCount = 0

    def check_enabled(self):
        """Check if the task is enabled."""
        self.checkEnabledCount += 1
        if self.checkEnabledCount % 6 != 1:
            return
        page = pywikibot.Page(
            self.site,
            'User:%s/shutoff/%s' % (self.site.user(), self.__class__.__name__)
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                sys.exit('%s disabled:\n%s' %
                         (self.__class__.__name__, content))

    def treat_page(self):
        self.check_enabled()

        pageConfig = self.config[self.current_page.title()]
        addedCount = 0
        removedCount = 0
        renamedCount = 0
        text = self.current_page.get().strip()
        pageJSON = json.loads(text, object_pairs_hook=OrderedDict)
        pageDict = {
            '>nonusers': set()
        }

        # Process the current targets.
        for item in pageJSON['targets']:
            page = pywikibot.Page(self.site, item['title'])
            if page.namespace().id not in (2, 3):
                pageDict['>nonusers'].add(page)
                continue
            basePage = pywikibot.Page(
                self.site,
                re.sub(r'^([^/]+).*', r'\1', page.title())
            )
            if basePage.isTalkPage:
                user = pywikibot.User(basePage.toggleTalkPage())
            else:
                user = pywikibot.User(basePage)
            # Handle renames.
            for rename in self.renames:
                if user != rename['olduser']:
                    continue
                newuser = rename['newuser']
                newpage = pywikibot.Page(
                    self.site,
                    re.sub(r':%s\b' % user.title(withNamespace=False),
                           r':%s' % newuser.title(withNamespace=False),
                           page.title())
                )
                pywikibot.log('%s renamed to %s (%s to %s)' % (
                    user.title(),
                    newuser.title(),
                    page.title(),
                    newpage.title()
                ))
                user = newuser
                page = newpage
                renamedCount += 1
            if pageConfig.get('required', None):
                if not pageConfig['group'] & set(user.groups()):
                    pywikibot.log(
                        'Removed %s, not in required group' % user.title())
                    removedCount += 1
                    continue
            pageDict[user] = page

        # Handle group changes.
        for change in self.groupChanges:
            user = change['user']
            if (pageConfig.get('add', None) and
                    (pageConfig['group'] & change['added']) and
                    'bot' not in user.groups() and
                    user not in pageDict
                ):
                pywikibot.log('Added %s' % user.title())
                pageDict[user] = user.toggleTalkPage()
                addedCount += 1
            if (pageConfig.get('remove', None) and
                    (pageConfig['group'] & change['removed'])
                ):
                if pageDict.pop(user, None):
                    pywikibot.log('Removed %s' % user.title())
                    removedCount += 1

        # Build JSON and save.
        if addedCount > 0 or removedCount > 0 or renamedCount > 0:
            newPageJSON = OrderedDict()
            newPageJSON['description'] = pageJSON['description']
            newPageJSON['targets'] = []
            for page in sorted(pageDict.pop('>nonusers') |
                               set(pageDict.values())):
                newPageJSON['targets'].append({'title': page.title()})
            newtext = json.dumps(newPageJSON, ensure_ascii=False, indent=4)
            summary = ('Update MassMessage list: %s added, %s removed' %
                       (addedCount, removedCount))
            if renamedCount > 0:
                summary += ', %s renamed' % renamedCount
            self.put_current(newtext, summary=summary, minor=False)


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'endDate': date.today() - timedelta(days=1),
        'startDate': date.today() - timedelta(days=1)
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    for arg in local_args:
        arg, sep, value = arg.partition(':')
        option = arg[1:]
        if option in (
            'config',
            'endDate',
            'startDate'
        ):
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[option] = value
        else:
            options[option] = True
    if not validate_options(options, site):
        pywikibot.bot.suggest_help(
            additional_text='The specified options are invalid.')
        return False
    config = pywikibot.Page(site, options.pop('config')).get()
    config = json.loads(config)
    if not validate_config(config, site):
        pywikibot.bot.suggest_help(
            additional_text='The specified configuration is invalid.')
        return False
    options['config'] = config

    meta = pywikibot.Site('meta', 'meta')
    suffix = '@%s' % site.dbName()
    start = datetime.datetime.combine(options.pop('startDate'), time.min)
    end = datetime.datetime.combine(options.pop('endDate'), time.max)
    # Parse rename logs into a list of dict.
    if options.pop('rename', None):
        renames = []
        if options.get('meta', None):
            renameevents = meta.logevents(logtype='gblrename', start=start,
                                          end=end, reverse=True)
        else:
            renameevents = site.logevents(logtype='renameuser', start=start,
                                          end=end, reverse=True)
        for rename in renameevents:
            try:
                renames.append({
                    'olduser':
                        pywikibot.User(site, rename._params['olduser']),
                    'newuser':
                        pywikibot.User(site, rename._params['newuser']),
                    'timestamp': rename.timestamp()
                })
            except KeyError:
                continue
        options['renames'] = sorted(renames, key=itemgetter('timestamp'))

    # Parse rights logs into a list of dict.
    groupChanges = []
    logevents = site.logevents(logtype='rights', start=start, end=end,
                               reverse=True)
    if options.pop('meta', None):
        metaLogevents = meta.logevents(logtype='rights', start=start, end=end,
                                       reverse=True)
        metaLogevents = (logevent for logevent in metaLogevents
                         if logevent.page().title().endswith(suffix))
        logevents = chain(logevents, metaLogevents)
    for logevent in logevents:
        newgroups = set(logevent.newgroups)
        oldgroups = set(logevent.oldgroups)
        try:
            groupChanges.append({
                'user': pywikibot.User(site, re.sub(r'%s$' % suffix, '',
                                                    logevent.page().title())),
                'added': newgroups - oldgroups,
                'removed': oldgroups - newgroups,
                'timestamp': logevent.timestamp()
            })
        except KeyError:
            continue
    options['groupChanges'] = sorted(groupChanges,
                                     key=itemgetter('timestamp'))

    # Generate pages and invoke the bot.
    gen = (config[key]['page'] for key in config.keys()
           if config[key]['enabled'])
    gen = pagegenerators.PreloadingGenerator(gen)
    bot = UserGroupsMassMessageListUpdater(gen, **options)
    bot.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
