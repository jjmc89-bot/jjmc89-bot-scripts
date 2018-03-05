#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script updates user groups MassMessage lists.

The following parameters are required:

-config           The page title that has the JSON config (object)

The following parameters are supported:

-end_date         Logs will be parsed starting on this date. The default is
                  yesterday. Format: YYYY-MM-DD.

-meta             metawiki will also be checked for group changes. Should be
                  specified when running on WMF wikis with CentralAuth.

-rename           Rename logs will be parsed. If -meta from metawiki.

-start_date       Logs will be parsed ending on this date. The default is
                  yesterday. Format: YYYY-MM-DD.
"""
# Author : JJMC89
# License: MIT
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


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict or None
    """
    if not page.exists():
        pywikibot.error('%s does not exist.' % page.title())
        return None
    elif page.isRedirectPage():
        pywikibot.error('%s is a redirect.' % page.title())
        return None
    elif page.isEmpty():
        pywikibot.log('%s is empty.' % page.title())
        return None
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error('%s does not contain valid JSON.' % page.title())
        raise


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
    for title, page_config in config.items():
        pywikibot.log('-%s: %s' % (title, page_config))
        page_config['page'] = pywikibot.Page(site, title)
        required_keys = ['enabled', 'group', 'page']
        has_keys = list()
        for key, value in page_config.items():
            if key in required_keys:
                has_keys.append(key)
            if key in 'add' 'enabled' 'remove' 'required':
                if not isinstance(value, bool):
                    return False
            elif key == 'group':
                if isinstance(value, str):
                    page_config[key] = set([value])
                else:
                    return False
            elif key == 'page':
                if value.content_model != 'MassMessageListContent':
                    return False
            else:
                return False
        if sorted(has_keys) != sorted(required_keys):
            return False
    return True


def validate_options(options):
    """
    Validate the options and return bool.

    @param options: options to validate
    @type options: dict

    @rtype: bool
    """
    pywikibot.log('Options:')
    required_keys = ['config', 'end_date', 'start_date']
    has_keys = list()
    for key in ('end_date', 'start_date'):
        if key not in options:
            continue
        value = options[key]
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
        options[key] = value
    for key, value in options.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in required_keys:
            has_keys.append(key)
        if key == 'config':
            if not isinstance(value, str):
                return False
        elif key in 'end_date' 'start_date':
            if not isinstance(value, datetime.date):
                return False
    if sorted(has_keys) != sorted(required_keys):
        return False
    return True


class UserGroupsMassMessageListUpdater(
        SingleSiteBot,
        ExistingPageBot,
        NoRedirectPageBot
):
    """Bot to update MassMessage lists."""

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'config': dict(),
            'group_changes': list(),
            'renames': [{
                'olduser': None,
                'newuser': None,
                'timestamp': None
            }]
        })
        self.generator = generator
        super().__init__(**kwargs)

    def check_enabled(self):
        """Check if the task is enabled."""
        if self._treat_counter % 6 != 0:
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
        """Process one page."""
        self.check_enabled()

        page_config = self.getOption('config')[self.current_page.title()]
        added_count = removed_count = renamed_count = 0
        page_json = json.loads(self.current_page.text,
                               object_pairs_hook=OrderedDict)
        page_dict = {'>nonusers': set()}

        # Process the current targets.
        for item in page_json['targets']:
            page = pywikibot.Page(self.site, item['title'])
            if page.namespace().id not in (2, 3):
                page_dict['>nonusers'].add(page)
                continue
            base_page = pywikibot.Page(
                self.site,
                re.sub(r'^([^/]+).*', r'\1', page.title())
            )
            if base_page.isTalkPage:
                user = pywikibot.User(base_page.toggleTalkPage())
            else:
                user = pywikibot.User(base_page)
            # Handle renames.
            for rename in self.getOption('renames'):
                if user != rename['olduser']:
                    continue
                newuser = rename['newuser']
                newpage = pywikibot.Page(
                    self.site,
                    re.sub(r':%s\b' % re.escape(
                        user.title(withNamespace=False)),
                           ':%s' % newuser.title(withNamespace=False),
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
                renamed_count += 1
            if page_config.get('required', None):
                if not page_config['group'] & set(user.groups()):
                    pywikibot.log(
                        'Removed %s, not in required group' % user.title())
                    removed_count += 1
                    continue
            page_dict[user] = page

        # Handle group changes.
        for change in self.getOption('group_changes'):
            user = change['user']
            if (page_config.get('add', None)
                    and (page_config['group'] & change['added'])
                    and 'bot' not in user.groups()
                    and user not in page_dict
               ):
                pywikibot.log('Added %s' % user.title())
                page_dict[user] = user.toggleTalkPage()
                added_count += 1
            if (page_config.get('remove', None)
                    and (page_config['group'] & change['removed'])
               ):
                if page_dict.pop(user, None):
                    pywikibot.log('Removed %s' % user.title())
                    removed_count += 1

        # Build JSON and save.
        if added_count + removed_count + renamed_count > 0:
            new_pge_json = OrderedDict()
            new_pge_json['description'] = page_json['description']
            new_pge_json['targets'] = list()
            for page in sorted(page_dict.pop('>nonusers') |
                               set(page_dict.values())):
                new_pge_json['targets'].append({'title': page.title()})
            text = json.dumps(new_pge_json, ensure_ascii=False, indent=4)
            summary = ('Update MassMessage list: %s added, %s removed' %
                       (added_count, removed_count))
            if renamed_count > 0:
                summary += ', %s renamed' % renamed_count
            self.put_current(text, summary=summary, minor=False)


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'end_date': date.today() - timedelta(days=1),
        'start_date': date.today() - timedelta(days=1)
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    for arg in local_args:
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg in 'config' 'end_date' 'start_date':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if not validate_options(options):
        pywikibot.bot.suggest_help(
            additional_text='The specified options are invalid.')
        return False
    config = pywikibot.Page(site, options.pop('config'))
    config = get_json_from_page(config)
    if not validate_config(config, site):
        pywikibot.bot.suggest_help(
            additional_text='The specified configuration is invalid.')
        return False
    options['config'] = config

    meta = pywikibot.Site('meta', 'meta')
    suffix = '@%s' % site.dbName()
    start = datetime.datetime.combine(options.pop('start_date'), time.min)
    end = datetime.datetime.combine(options.pop('end_date'), time.max)
    # Parse rename logs into a list of dict.
    if options.pop('rename', None):
        renames = list()
        if options.get('meta', None):
            rename_events = meta.logevents(logtype='gblrename', start=start,
                                           end=end, reverse=True)
        else:
            rename_events = site.logevents(logtype='renameuser', start=start,
                                           end=end, reverse=True)
        for rename in rename_events:
            try:
                renames.append({
                    'olduser':
                        pywikibot.User(site, rename.data['params']['olduser']),
                    'newuser':
                        pywikibot.User(site, rename.data['params']['newuser']),
                    'timestamp': rename.timestamp()
                })
            except KeyError:
                continue
        options['renames'] = sorted(renames, key=itemgetter('timestamp'))

    # Parse rights logs into a list of dict.
    group_changes = list()
    rights_events = site.logevents(logtype='rights', start=start, end=end,
                                   reverse=True)
    if options.pop('meta', None):
        meta_rights_events = meta.logevents(logtype='rights', start=start,
                                            end=end, reverse=True)
        meta_rights_events = (log_event for log_event in meta_rights_events
                              if log_event.page().title().endswith(suffix))
        rights_events = chain(rights_events, meta_rights_events)
    for log_event in rights_events:
        try:
            new_groups = set(log_event.newgroups)
            old_groups = set(log_event.oldgroups)
            group_changes.append({
                'user': pywikibot.User(site, re.sub(r'%s$' % suffix, '',
                                                    log_event.page().title())),
                'added': new_groups - old_groups,
                'removed': old_groups - new_groups,
                'timestamp': log_event.timestamp()
            })
        except KeyError:
            continue
    options['group_changes'] = sorted(group_changes,
                                      key=itemgetter('timestamp'))

    # Generate pages and invoke the bot.
    gen = (config[key]['page'] for key in config.keys()
           if config[key]['enabled'])
    gen = pagegenerators.PreloadingGenerator(gen)
    bot = UserGroupsMassMessageListUpdater(gen, **options)
    bot.run()
    return True


if __name__ == "__main__":
    main()
