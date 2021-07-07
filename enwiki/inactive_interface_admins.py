#!/usr/bin/env python3
"""
This script reports inactive interface admins.
"""
# Author : JJMC89
# License: MIT
from functools import lru_cache
from itertools import chain
from typing import Optional, Set, Tuple, Union

import pywikibot
from dateutil.relativedelta import relativedelta
from pywikibot.logentries import LogEntry


PageSource = Union[
    pywikibot.Page, pywikibot.site.BaseSite, pywikibot.page.BaseLink
]
UserContrib = Tuple[pywikibot.Page, int, pywikibot.Timestamp, str]


def get_inactive_users(
    site: pywikibot.site.APISite = None,
) -> Set[pywikibot.User]:
    """
    Get a set of inactive interface admins.

    :param site: site to work on
    """
    users = set()
    if not site:
        site = pywikibot.Site()
    for user_dict in site.allusers(group='interface-admin'):
        user = User(site, user_dict['name'])
        if not user.is_active:
            users.add(user)
    return users


class User(pywikibot.User):
    """Extended pywikibot.User."""

    @property
    def is_active(self) -> bool:
        """
        True if the user is active, False otherwise.

        A user is active if they have both
         1) a CSS/JS edit in the last 6 months
         2) an edit or log entry in the last 2 months
        """
        cutoff = self.site.server_time() + relativedelta(months=-2)
        if self.has_cssjs_edit is False:
            return False
        if self.last_edit and self.last_edit[2] >= cutoff:
            return True
        if self.last_event and self.last_event.timestamp() >= cutoff:
            return True
        return False

    @property
    @lru_cache()
    def last_edit(self) -> Optional[UserContrib]:
        """The user's last edit."""
        return super().last_edit

    @property
    @lru_cache()
    def last_event(self) -> Optional[LogEntry]:
        """The user's last log entry."""
        return super().last_event

    @property
    @lru_cache()
    def has_cssjs_edit(self) -> Optional[bool]:
        """
        True if the user has edited a CSS/JS page in the last 6 months.

        None if the user has not been an interface-admin for 6 months.
        False otherwise.
        """
        kwa = dict(
            namespaces=(2, 8),
            end=self.site.server_time() + relativedelta(months=-6),
        )
        for page, _, _, summary in self.contributions(total=None, **kwa):
            if not (
                page.content_model not in ('css', 'javascript')
                or page.title().startswith('{}/'.format(self.title()))
                or 'while renaming the user' in summary
            ):
                return True
        pywikibot.log('{}: No CSS/JS edit'.format(self.username))
        got_group = kwa['end']
        rights_events = sorted(
            chain(
                self.site.logevents(logtype='rights', page=self),
                pywikibot.Site('meta', 'meta').logevents(
                    logtype='rights',
                    page='{}@{}'.format(self.title(), self.site.dbName()),
                ),
            ),
            key=lambda logevent: logevent.timestamp(),
            reverse=True,
        )
        for logevent in rights_events:
            added_groups = set(logevent.newgroups) - set(
                logevent.oldgroups
            )
            if 'interface-admin' in added_groups:
                got_group = logevent.timestamp()
                break
        if kwa['end'] < got_group:
            pywikibot.log('{}: Not iadmin for 6 mo.'.format(self.username))
            return None
        return False


def main(*args: str) -> None:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    users = get_inactive_users(site=site)
    if not users:
        return
    heading = 'Inactive interface administrators {}'.format(
        site.server_time().date().isoformat()
    )
    text = 'The following interface administrator(s) are inactive:'
    for user in sorted(users):
        text += '\n* {{{{admin|1={}}}}}'.format(user.username)
    text += '\n~~~~'
    pywikibot.Page(
        site, "Wikipedia:Interface administrators' noticeboard"
    ).save(text=text, section='new', summary=heading, botflag=False)


if __name__ == '__main__':
    main()
