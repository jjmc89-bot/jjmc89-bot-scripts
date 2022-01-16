#!/usr/bin/env python3
"""Update user groups MassMessage lists."""
# Author : JJMC89
# License: MIT
from __future__ import annotations

import argparse
import datetime
import json
import re
from collections import OrderedDict
from contextlib import suppress
from datetime import date, time, timedelta
from itertools import chain
from operator import itemgetter
from typing import Any, Dict, Set, Union

import pywikibot
from pywikibot.bot import (
    _GLOBAL_HELP,
    ExistingPageBot,
    NoRedirectPageBot,
    SingleSiteBot,
)
from pywikibot.pagegenerators import PreloadingGenerator
from typing_extensions import TypedDict


PageDict = Dict[
    Union[str, pywikibot.User], Union[pywikibot.Page, Set[pywikibot.Page]]
]


class GroupChange(TypedDict):
    """Group change."""

    user: pywikibot.User
    added: set[str]
    removed: set[str]
    timestamp: pywikibot.Timestamp


class Rename(TypedDict):
    """Rename."""

    olduser: pywikibot.User
    newuser: pywikibot.User
    timestamp: pywikibot.Timestamp


class UserGroupsMassMessageListUpdater(
    SingleSiteBot, NoRedirectPageBot, ExistingPageBot
):
    """Bot to update MassMessage lists."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize."""
        self.available_options.update(  # pylint: disable=no-member
            {
                "config": {},
                "group_changes": [],
                "renames": [
                    {"olduser": None, "newuser": None, "timestamp": None}
                ],
            }
        )
        super().__init__(**kwargs)

    def check_disabled(self) -> None:
        """Check if the task is disabled. If so, quit."""
        class_name = self.__class__.__name__
        page = pywikibot.Page(
            self.site,
            f"User:{self.site.username()}/shutoff/{class_name}.json",
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                pywikibot.error(f"{class_name} disabled:\n{content}")
                self.quit()

    def treat_page(self) -> None:
        """Process one page."""
        self.check_disabled()

        page_config = self.opt.config[self.current_page.title()]
        added_count = removed_count = renamed_count = 0
        page_json = json.loads(
            self.current_page.text, object_pairs_hook=OrderedDict
        )
        page_dict: PageDict = {">nonusers": set()}

        # Process the current targets.
        for item in page_json["targets"]:
            page = pywikibot.Page(self.site, item["title"])
            if page.namespace().id not in (2, 3):
                page_dict[">nonusers"].add(page)
                continue
            base_page = pywikibot.Page(
                self.site, re.sub(r"^([^/]+).*", r"\1", page.title())
            )
            if base_page.isTalkPage():
                user = pywikibot.User(base_page.toggleTalkPage())
            else:
                user = pywikibot.User(base_page)
            # Handle renames.
            for rename in self.opt.renames:
                if user != rename["olduser"]:
                    continue
                newuser = rename["newuser"]
                newpage = pywikibot.Page(
                    self.site,
                    re.sub(
                        fr":{re.escape(user.title(with_ns=False))}\b",
                        f":{newuser.title(with_ns=False)}",
                        page.title(),
                    ),
                )
                pywikibot.log(
                    f"{user.title()} renamed to {newuser.title()} "
                    f"({page.title()} to {newpage.title()})"
                )
                user = newuser
                page = newpage
                renamed_count += 1
            if page_config.get("required", None):
                if not page_config["group"] & set(user.groups()):
                    pywikibot.log(f"Removed {user}, not in required group")
                    removed_count += 1
                    continue
            page_dict[user] = page

        # Handle group changes.
        for change in self.opt.group_changes:
            user = change["user"]
            if (
                page_config.get("add", None)
                and (page_config["group"] & change["added"])
                and "bot" not in user.groups()
                and user not in page_dict
            ):
                pywikibot.log(f"Added {user.title()}")
                page_dict[user] = user.toggleTalkPage()
                added_count += 1
            if page_config.get("remove", None) and (
                page_config["group"] & change["removed"]
            ):
                if page_dict.pop(user, None):
                    pywikibot.log(f"Removed {user.title()}")
                    removed_count += 1

        # Build JSON and save.
        if added_count or removed_count or renamed_count:
            new_page_json = OrderedDict()
            new_page_json["description"] = page_json["description"]
            new_page_json["targets"] = []
            for page in sorted(
                page_dict.pop(">nonusers") | set(page_dict.values())
            ):
                new_page_json["targets"].append({"title": page.title()})
            text = json.dumps(new_page_json, ensure_ascii=False, indent=4)
            if added_count + removed_count + renamed_count == 0:
                return
            summary_parts = []
            if added_count > 0:
                summary_parts.append(f"{added_count} added")
            if removed_count > 0:
                summary_parts.append(f"{removed_count} removed")
            if renamed_count > 0:
                summary_parts.append(f"{renamed_count} renamed")
            summary = f"Update MassMessage list: {','.join(summary_parts)}"
            self.put_current(text, summary=summary, minor=False)


def make_arg_parser() -> argparse.ArgumentParser:
    """Return the argument parser."""
    parser = argparse.ArgumentParser(
        description="Update user groups MassMessage lists",
        epilog=re.sub(
            r"\n\n?-help +.+?(\n\n-|\s*$)",
            r"\1",
            _GLOBAL_HELP,
            flags=re.S,
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "config",
        help="Page title that has the JSON config (object)",
    )
    parser.add_argument(
        "--always",
        "-a",
        action="store_true",
        help="Do not prompt to save changes",
    )
    parser.add_argument(
        "--meta",
        action="store_true",
        help=(
            "metawiki will also be checked for group changes. "
            "Should be specified when running on WMF wikis with CentralAuth."
        ),
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help="Rename logs will be parsed. If --meta, from metawiki.",
    )
    yesterday = date.today() - timedelta(days=1)
    parser.add_argument(
        "--start",
        default=datetime.datetime.combine(yesterday, time.min),
        type=pywikibot.Timestamp.fromISOformat,
        help="Timestamp to start from",
        metavar="%Y-%m-%dT%H:%M:%SZ",
    )
    parser.add_argument(
        "--end",
        default=datetime.datetime.combine(yesterday, time.max),
        type=pywikibot.Timestamp.fromISOformat,
        help="Timestamp to end at",
        metavar="%Y-%m-%dT%H:%M:%SZ",
    )
    return parser


def get_json_from_page(page: pywikibot.Page) -> dict[str, Any]:
    """
    Return JSON from the page.

    :param page: Page to read
    """
    if not page.exists():
        pywikibot.error(f"{page!r} does not exist.")
        return {}
    if page.isRedirectPage():
        pywikibot.error(f"{page!r} is a redirect.")
        return {}
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error(f"{page!r} does not contain valid JSON.")
        raise


def validate_config(
    config: dict[str, Any], site: pywikibot.site.APISite
) -> bool:
    """
    Validate the configuration and return bool.

    :param config: configuration to validate
    :param site: site used in the validation
    """
    pywikibot.log("config:")
    for title, page_config in config.items():
        pywikibot.log(f"-{title} = {page_config}")
        page_config["page"] = pywikibot.Page(site, title)
        required_keys = ["enabled", "group", "page"]
        has_keys = []
        for key, value in page_config.items():
            if key in required_keys:
                has_keys.append(key)
            if key in ("add", "enabled", "remove", "required"):
                if not isinstance(value, bool):
                    return False
            elif key == "group":
                if isinstance(value, str):
                    page_config[key] = {value}
                else:
                    return False
            elif key == "page":
                if value.content_model != "MassMessageListContent":
                    return False
            else:
                return False
        if sorted(has_keys) != sorted(required_keys):
            return False
    return True


def get_renames(
    rename_site: pywikibot.site.APISite,
    logtype: str,
    start: datetime.datetime,
    end: datetime.datetime,
    site: pywikibot.site.APISite,
) -> list[Rename]:
    """Retrun a sorted list of reenames."""
    renames = []
    rename_events = rename_site.logevents(
        logtype=logtype, start=start, end=end, reverse=True
    )
    for rename in rename_events:
        with suppress(KeyError):
            renames.append(
                Rename(
                    olduser=pywikibot.User(
                        site, rename.data["params"]["olduser"]
                    ),
                    newuser=pywikibot.User(
                        site, rename.data["params"]["newuser"]
                    ),
                    timestamp=rename.timestamp(),
                )
            )
    return sorted(renames, key=itemgetter("timestamp"))


def get_group_changes(
    site: pywikibot.site.APISite,
    start: datetime.datetime,
    end: datetime.datetime,
    meta: pywikibot.site.APISite | None,
) -> list[GroupChange]:
    """Return a sorted list of group canges."""
    group_changes = []
    rights_events = site.logevents(
        logtype="rights", start=start, end=end, reverse=True
    )
    if meta:
        meta_rights_events = set()
        for log_event in meta.logevents(
            logtype="rights", start=start, end=end, reverse=True
        ):
            try:
                if log_event.page().title().endswith(site.suffix):
                    meta_rights_events.add(log_event)
            except KeyError:
                continue
        rights_events = chain(rights_events, meta_rights_events)
    for log_event in rights_events:
        with suppress(KeyError):
            new_groups = set(log_event.newgroups)
            old_groups = set(log_event.oldgroups)
            group_changes.append(
                GroupChange(
                    user=pywikibot.User(
                        site,
                        re.sub(
                            fr"{site.suffix}$",
                            "",
                            log_event.page().title(),
                        ),
                    ),
                    added=new_groups - old_groups,
                    removed=old_groups - new_groups,
                    timestamp=log_event.timestamp(),
                )
            )
    return sorted(group_changes, key=itemgetter("timestamp"))


def main(*args: str) -> None:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    local_args = pywikibot.handle_args(args, do_help=False)
    site = pywikibot.Site()
    site.login()
    site.suffix = f"@{site.dbName()}"
    parser = make_arg_parser()
    options = vars(parser.parse_args(args=local_args))
    config_page = pywikibot.Page(site, options.pop("config"))
    config = get_json_from_page(config_page)
    if not validate_config(config, site):
        pywikibot.error("The specified configuration is invalid.")
        return
    options["config"] = config
    meta = pywikibot.Site("meta", "meta") if options.pop("meta") else None
    start = options.pop("start")
    end = options.pop("end")
    if options.pop("rename"):
        options["renames"] = get_renames(
            rename_site=meta or site,
            logtype="gblrename" if meta else "renameuser",
            start=start,
            end=end,
            site=site,
        )
    options["group_changes"] = get_group_changes(site, start, end, meta)
    gen = PreloadingGenerator(
        config[key]["page"] for key in config if config[key]["enabled"]
    )
    UserGroupsMassMessageListUpdater(generator=gen, site=site, **options).run()


if __name__ == "__main__":
    main()
