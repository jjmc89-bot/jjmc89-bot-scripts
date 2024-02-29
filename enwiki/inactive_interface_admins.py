"""Report inactive interface admins."""

from __future__ import annotations

from functools import cached_property
from itertools import chain

import pywikibot
from dateutil.relativedelta import relativedelta
from pywikibot.logentries import LogEntry


UserContrib = tuple[pywikibot.Page, int, pywikibot.Timestamp, str]


def get_inactive_users(
    site: pywikibot.site.APISite = None,
) -> set[pywikibot.User]:
    """
    Get a set of inactive interface admins.

    :param site: site to work on
    """
    users = set()
    if not site:
        site = pywikibot.Site()
    for user_dict in site.allusers(group="interface-admin"):
        user = User(site, user_dict["name"])
        if not user.is_active:
            users.add(user)
    return users


class User(pywikibot.User):
    """Extended pywikibot.User."""

    @cached_property
    def is_active(self) -> bool:
        """
        Return True if the user is active, False otherwise.

        A user is active if they have both
         1) a CSS/JS edit in the last year
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

    @cached_property
    def last_edit(self) -> UserContrib | None:
        """Return the user's last edit."""
        return super().last_edit

    @cached_property
    def last_event(self) -> LogEntry | None:
        """Return the user's last log entry."""
        return super().last_event

    @cached_property
    def has_cssjs_edit(self) -> bool | None:
        """
        Return True if the user has edited a CSS/JS page in the last year.

        None if the user has not been an interface-admin for 1 year.
        False otherwise.
        """
        kwa = {
            "namespaces": (2, 8),
            "end": self.site.server_time() + relativedelta(years=-1),
        }
        for page, _, _, summary in self.contributions(total=None, **kwa):
            if not (
                page.content_model not in ("css", "javascript")
                or page.title().startswith(f"{self.title()}/")
                or "while renaming the user" in summary
            ):
                return True
        pywikibot.log(f"{self!r}: No CSS/JS edit")
        got_group = kwa["end"]
        for logevent in sorted(
            chain(
                self.site.logevents(logtype="rights", page=self),
                pywikibot.Site("meta", "meta").logevents(
                    logtype="rights",
                    page=f"{self.title()}@{self.site.dbName()}",
                ),
            ),
            key=lambda logevent: logevent.timestamp(),
            reverse=True,
        ):
            added_groups = set(logevent.newgroups) - set(logevent.oldgroups)
            if "interface-admin" in added_groups:
                got_group = logevent.timestamp()
                break
        if kwa["end"] < got_group:
            pywikibot.log(f"{self!r}: Not iadmin for 1 year.")
            return None
        return False


def main(*args: str) -> int:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    users = get_inactive_users(site=site)
    if not users:
        return 0
    heading = (
        "Inactive interface administrators "
        f"{site.server_time().date().isoformat()}"
    )
    text = "The following interface administrator(s) are inactive:"
    for user in sorted(users):
        text += f"\n* {{{{admin|1={user.username}}}}}"
    text += "\n~~~~"
    pywikibot.Page(
        site, "Wikipedia:Interface administrators' noticeboard"
    ).save(text=text, section="new", summary=heading, botflag=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
