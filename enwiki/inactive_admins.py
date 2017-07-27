#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script reports and notifies inactive admins.


The following parameters are required:

-config           The page title that has the JSON config (object).
"""
# Author : JJMC89
# License: MIT
import json
import re
from datetime import date
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
import mwparserfromhell
import pywikibot


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict
    """
    if page.isRedirectPage():
        pywikibot.log('%s is a redirect.' % page.title())
        page = page.getRedirectTarget()
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error('{} does not contain valid JSON.'.format(page.title()))
        raise


def validate_options(options):
    """
    Validate the options and return bool.

    @param options: options to validate
    @type options: dict

    @rtype: bool
    """
    pywikibot.log('Options:')
    notice_keys = ['email_subject', 'email_subject2', 'email_text',
                   'email_text2', 'note_summary', 'note_summary2', 'note_text',
                   'note_text2']
    required_keys = notice_keys + ['date', 'exclusions']
    has_keys = list()
    result = True
    for key, value in options.items():
        pywikibot.log('-{} = {}'.format(key, value))
        if key in required_keys:
            has_keys.append(key)
        if key == 'date':
            if not isinstance(value, date):
                result = False
        elif key == 'exclusions':
            if isinstance(value, str):
                options[key] = [value]
            elif not isinstance(value, list):
                result = False
            else:
                for item in value:
                    if not isinstance(item, str):
                        result = False
        elif key == 'max_attempts':
            if not isinstance(value, int):
                result = False
        elif key in notice_keys:
            if not isinstance(value, str):
                result = False
        else:
            result = False
    if sorted(has_keys) != sorted(required_keys):
        result = False
    return result


def get_inactive_users(cutoff, exclusions, group=None, site=None):
    """
    Get a set of inactive users.

    @param exclusions: List of users to exclude
    @type exclusions: list
    @param site: site to work on
    @type site: L{pywikibot.Site}
    @param group: only include users that are members of this group
    @type group: str

    @rtype: set
    """
    users = set()
    if not site:
        site = pywikibot.Site()
    for user_dict in site.allusers(group=group):
        name = user_dict['name']
        if name not in exclusions:
            user = User(site, name)
            if not user.is_active(cutoff=cutoff):
                users.add(user)
    return users


def create_section(options, site=None):
    """
    Create a section of inactive admins and notify them.

    @param options: Bot options
    @type options: dict

    @rtype: str
    """
    inactive_sysops = get_inactive_users(
        options['date'] + relativedelta(years=-1),
        options['exclusions'],
        site=site,
        group='sysop'
    )
    text = '\n=== {date:%B %Y} ===\n'.format(**options)
    if inactive_sysops:
        text += (
            '{{{{hatnote|Administrators listed below may have their '
            'permissions removed on or after {date.day} {date:%B %Y} (UTC)'
            ' after being duly notified.}}}}\n{{{{iarow/t}}}}\n'
            .format(**options)
        )
        for user in inactive_sysops:
            tpl = mwparserfromhell.nodes.Template('iarow')
            tpl.add('1', user.username)
            if user.last_edit:
                tpl.add('lastedit', '{date.day} {date:%B %Y}'
                        .format(date=user.last_edit[2].date()))
            if user.last_log_entry:
                tpl.add('lastlog', '{date.day} {date:%B %Y}'
                        .format(date=user.last_log_entry.timestamp().date()))
            user.notify(options)
            for param, value in user.notifications.items():
                if value:
                    tpl.add(param, value)
            text += str(tpl) + '\n'
        text += '{{iarow/b}}'
    else:
        text += ': None'
    text += '\n\n'
    return text


def update_section(text, options, site=None):
    """
    Update the specified section.
    Active admins are removed and second notifications sent one week
    before the date in the section.

    @param text: Text of the section
    @type text: str
    @param options: Bot options
    @type options: dict

    @rtype: str
    """
    if not site:
        site = pywikibot.Site()
    wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
    if not wikicode.filter_templates(recursive=False, matches='iarow'):
        pywikibot.log('No inactive admins.')
        return text
    inactive_sysops = 0
    match = re.match(r'.+?on or after \b(?P<date>.+?) \(UTC\)',
                     text, flags=re.S)
    if match:
        section_date = parse(match.group('date')).date()
    else:
        raise ValueError('Could not find a valid date.')
    for tpl in wikicode.ifilter_templates(recursive=False):
        if not tpl.name.matches('iarow'):
            continue
        if not tpl.has('1', ignore_empty=True):
            pywikibot.log('{tpl} has no user specified'.format(tpl=str(tpl)))
            wikicode.remove(tpl)
            continue
        user = User(site, tpl.get('1'))
        if user.is_active(cutoff=section_date + relativedelta(years=-1)):
            pywikibot.log('{user} is now active.'.format(user=user.username))
            wikicode.remove(tpl)
        else:
            inactive_sysops += 1
            if section_date + relativedelta(weeks=-1) == date.today():
                for param, value in user.notifications.items():
                    if tpl.has(param, ignore_empty=True):
                        user.notifications[param] = value
                user.notify(options, notice_number=2)
                for param, value in user.notifications.items():
                    if value and not tpl.has(param, ignore_empty=True):
                        tpl.add(param, value)
    if inactive_sysops == 0:
        for tpl in wikicode.ifilter_templates(recursive=False,
                                              matches='iarow'):
            wikicode.remove(tpl)
        text = str(wikicode) + '\n: None\n'
    else:
        text = str(wikicode)
    return re.sub(r'\n{2,}', r'\n', text)


def split_into_sections(text):
    """
    Splits wikitext into sections based on any level wiki heading.

    @param text: Text to split
    @type text: str

    @rtype: list
    """
    headings_regex = re.compile(r'^={1,6}.*?={1,6}(?: *<!--.*?-->)?\s*$',
                                flags=re.M)
    sections = list()
    last_match_start = 0
    for match in headings_regex.finditer(text):
        match_start = match.start()
        if match_start > 0:
            sections.append(text[last_match_start:match_start])
            last_match_start = match_start
    sections.append(text[last_match_start:])
    return sections


class User(pywikibot.User):
    """Extended L{pywikibot.User}."""

    def __init__(self, source, title):
        """
        Initializer for a User object.

        All parameters are the same as for L{pywikibot.User}.
        """
        super().__init__(source, title)
        self.notifications = {
            'email': None,
            'email2': None,
            'note': None,
            'diff': None,
            'note2': None,
            'diff2': None
        }
        self._last_edit = None
        self._is_active = None
        self._last_log_entry = None

    def is_active(self, cutoff=date.today() + relativedelta(years=-1)):
        """
        True if the user is active.
        A user is active if they have an edit or log entry since the cutoff.

        @param cutoff: Cutoff for user activity
        @type cutoff: datetime.date
        @rtype: bool
        """
        if self._is_active is None:
            if self.last_edit and self.last_edit[2].date() >= cutoff:
                self._is_active = True
            elif (self.last_log_entry
                  and self.last_log_entry.timestamp().date() >= cutoff):
                self._is_active = True
            else:
                self._is_active = False
        return self._is_active

    @property
    def last_edit(self):
        """
        The user's last edit.

        @rtype: tuple
        """
        if self._last_edit is None:
            self._last_edit = next(self.contributions(total=1), None)
        return self._last_edit

    @property
    def last_log_entry(self):
        """
        The user's last log entry.

        @rtype: L{pywikibot.logentry}
        """
        if self._last_log_entry is None:
            self._last_log_entry = next(iter(self.site.logevents(
                user=self.username, total=1)), None)
        return self._last_log_entry

    def notify(self, options, notice_number=1):
        """
        Notify the user.

        @param options: Bot options
        @type options: dict
        @param notice_number: Notice number
        @type notice_number: int
        """
        param_suffix = '' if notice_number == 1 else str(notice_number)
        talk_page = self.getUserTalkPage()
        if (self.notifications['note' + param_suffix]
                or self.notifications['email' + param_suffix]):
            return
        success = False
        attempts = 0
        while not success and attempts < options.get('max_attempts', 3):
            attempts += 1
            success = self.site.editpage(
                talk_page,
                summary=options['note_summary' + param_suffix],
                minor=False,
                bot=False,
                section='new',
                text=options['note_text' + param_suffix]
            )
            if not success:
                pywikibot.log(
                    'Failed to send {note} to {username}. Attempt: '
                    '{attempts}.'.format(note='note' + param_suffix,
                                         username=self.username,
                                         attempts=attempts)
                )
        if success:
            self.notifications['note' + param_suffix] = (
                '{date.day} {date:%B %Y}'.format(date=date.today()))
            self.notifications['diff' + param_suffix] = (
                str(talk_page.latest_revision_id))
        if self.isEmailable():
            success = False
            attempts = 0
            while not success and attempts < options.get('max_attempts', 3):
                attempts += 1
                success = self.send_email(
                    options['email_subject' + param_suffix],
                    options['email_text' + param_suffix]
                )
                if not success:
                    pywikibot.log(
                        'Failed to send {email} to {username}. Attempt: '
                        '{attempts}.'.format(email='email' + param_suffix,
                                             username=self.username,
                                             attempts=attempts)
                    )
            if success:
                self.notifications['email' + param_suffix] = (
                    '{date.day} {date:%B %Y}'.format(date=date.today()))
        else:
            pywikibot.log('{username} has email disabled.'
                          .format(username=self.username))
            self.notifications['email' + param_suffix] = 'no'


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'date': date.today() + relativedelta(months=1),
        'exclusions': list()
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    for arg in local_args:
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg == 'config':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if 'config' not in options:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    options.update(get_json_from_page(pywikibot.Page(site,
                                                     options.pop('config'))))
    if not validate_options(options):
        pywikibot.error('Invalid options.')
        return False
    page = pywikibot.Page(
        site,
        'Wikipedia:Inactive administrators/{date:%Y}'.format(**options)
    )
    sections = split_into_sections(page.text)
    section = None
    log_section = None
    for i, sect in enumerate(sections):
        sect_code = mwparserfromhell.parse(sect, skip_style_tags=True)
        heading = sect_code.filter(forcetype=mwparserfromhell.nodes.Heading)
        if not heading:
            continue
        heading = heading[0]
        if not log_section and heading.title.matches('Log'):
            log_section = i
        if heading.title.matches('{date:%B %Y}'.format(**options)):
            section = sect
            break
    if section:
        page.text = page.text.replace(
            str(section),
            update_section(str(section), options, site=site)
        )
        page.save(
            summary='Updating {date:%B %Y} inavtive admins'.format(**options),
            minor=False,
            botflag=False,
            force=True
        )
    else:
        options['exclusions'] += [
            user.username for user in
            page.linkedPages(namespaces=site.namespaces.USER.id)]
        section = create_section(options, site=site)
        if log_section:
            sections.insert(log_section + 1, section)
        else:
            sections.append(section)
        page.text = ''.join(str(i) for i in sections)
        page.save(
            summary='Reporting {date:%B %Y} inavtive admins'.format(**options),
            minor=False,
            botflag=False,
            force=True
        )


if __name__ == "__main__":
    main()
