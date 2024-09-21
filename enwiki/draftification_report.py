"""Generate a tabular report of draftifications over a specified range."""

from __future__ import annotations

import argparse
import datetime
import re
from collections.abc import Iterable
from contextlib import suppress
from datetime import time, timedelta

import pywikibot
from pywikibot.bot import _GLOBAL_HELP
from pywikibot.exceptions import InvalidTitleError
from pywikibot.pagegenerators import PrefixingPageGenerator
from pywikibot_extensions.page import Page
from pywikibot_extensions.textlib import iterable_to_wikitext


def get_xfds(pages: Iterable[pywikibot.Page]) -> set[str]:
    """Return a set of XfDs for the pages."""
    xfds: set[str] = set()
    for page in pages:
        if page.namespace() == page.site.namespaces.MAIN:
            prefix = "Articles for deletion/"
        else:
            prefix = "Miscellany for deletion/"
        prefix += page.title()
        with suppress(InvalidTitleError):
            gen = PrefixingPageGenerator(prefix, namespace=4, site=page.site)
            xfds = xfds.union(xfd_page.title(as_link=True) for xfd_page in gen)
    return xfds


def output_move_log(
    page: pywikibot.Page,
    *,
    start: datetime.datetime,
    end: datetime.datetime,
) -> None:
    """Write move logevents to a page."""
    text = ""
    for logevent in page.site.logevents(
        logtype="move",
        namespace=page.site.namespaces.MAIN.id,
        start=start,
        end=end,
        reverse=True,
    ):
        if logevent.target_ns not in (
            2,
            118,
        ) or logevent.target_title.startswith("Draft:Move/"):
            # Only want moves to Draft or User.
            # Skip page swaps.
            continue
        current_page = None
        creator = creation = last_edit = num_editors = "(Unknown)"
        if logevent.target_page.exists():
            current_page = logevent.target_page
            if current_page.isRedirectPage():
                try:
                    redirect_target = current_page.getRedirectTarget()
                except pywikibot.exceptions.CircularRedirectError:
                    pywikibot.log(f"{current_page!r} is a circular redirect.")
                else:
                    if redirect_target.exists() and (
                        redirect_target.namespace() in (0, 2, 118)
                    ):
                        current_page = redirect_target
        elif logevent.page().exists():
            current_page = logevent.page()
        if current_page:
            if current_page.oldest_revision.user:
                creator = f"[[User:{current_page.oldest_revision.user}]]"
            creation = (
                "[[Special:PermaLink/{rev.revid}|{rev.timestamp}]]".format(
                    rev=current_page.oldest_revision
                )
            )
            last_edit = "[[Special:Diff/{rev.revid}|{rev.timestamp}]]".format(
                rev=current_page.latest_revision
            )
            editors = set()
            for rev in current_page.revisions():
                if rev.user:
                    editors.add(rev.user)
            num_editors = str(len(editors))
        text += (
            "\n|-\n| {page} || {target} || [[User:{log[user]}]] || "
            "{log[timestamp]} || <nowiki>{log[comment]}</nowiki> || "
            "{creator} || {creation} || {editors} || {last_edit} || "
            "{notes}".format(
                page=logevent.page().title(as_link=True, textlink=True),
                target=logevent.target_page.title(as_link=True, textlink=True),
                log=logevent.data,
                creator=creator,
                creation=creation,
                editors=num_editors,
                last_edit=last_edit,
                notes=iterable_to_wikitext(
                    get_xfds([logevent.page(), logevent.target_page])
                ),
            )
        )
    if text:
        caption = f"Report for {start.date().isoformat()}"
        if start.date() != end.date():
            caption += f" to {end.date().isoformat()}"
        caption += "; Last updated: ~~~~~"
        text = (
            f'\n{{| class="wikitable sortable plainlinks"\n|+ {caption}'
            "\n! Page !! Target !! Mover !! Move date/time !! Move summary !! "
            f"Creator !! Creation !! Editors !! Last edit !! Notes{text}\n|}}"
        )
    else:
        text = "None"
    page.save_bot_start_end(text, summary="Updating draftification report")


def main(*args: str) -> int:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    local_args = pywikibot.handle_args(args, do_help=False)
    site = pywikibot.Site()
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=re.sub(
            r"\n\n?-help +.+?(\n\n-|\s*$)", r"\1", _GLOBAL_HELP, flags=re.S
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument("page", help="page to output the report to")
    yesterday = datetime.datetime.utcnow().date() - timedelta(days=1)
    parser.add_argument(
        "--start",
        default=datetime.datetime.combine(yesterday, time.min),
        type=pywikibot.Timestamp.fromISOformat,
        help="start timestamp of the range for the report",
        metavar="%Y-%m-%dT%H:%M:%SZ",
    )
    parser.add_argument(
        "--end",
        default=datetime.datetime.combine(yesterday, time.max),
        type=pywikibot.Timestamp.fromISOformat,
        help="end timestamp of the range for the report",
        metavar="%Y-%m-%dT%H:%M:%SZ",
    )
    parsed_args = parser.parse_args(args=local_args)
    site.login()
    output_move_log(
        page=Page(site, parsed_args.page),
        start=parsed_args.start,
        end=parsed_args.end,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
