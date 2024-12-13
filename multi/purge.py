"""Purge pages."""

from __future__ import annotations

import argparse
import re

import pywikibot
import pywikibot.exceptions
from pywikibot.bot import _GLOBAL_HELP, ExistingPageBot, MultipleSitesBot
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp


class PurgeBot(MultipleSitesBot, ExistingPageBot):
    """Purge bot."""

    available_options = {
        "converttitles": None,
        "forcelinkupdate": None,
        "forcerecursivelinkupdate": None,
        "redirects": None,
    }

    def treat_page(self) -> None:
        """Process one page."""
        try:
            if self.current_page.purge(**self.opt):
                pywikibot.info(f"Purged {self.current_page!r}")
            else:
                pywikibot.error("Failed to purge {self.current_page}")
        except (
            pywikibot.exceptions.ServerError,
            pywikibot.exceptions.TimeoutError,
        ):
            pywikibot.exception()


def main(*args: str) -> int:
    """Parse arguments and run the bot."""
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    gen_factory = GeneratorFactory()
    script_args = gen_factory.handle_args(local_args)
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=parameterHelp
        + re.sub(
            r"\n\n?-help +.+?(\n\n-|\s*$)",
            r"\1",
            _GLOBAL_HELP,
            flags=re.S,
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--converttitles",
        action="store_true",
        help="Convert titles to other variants if necessary and supported",
    )
    forcelinkupdate_group = parser.add_mutually_exclusive_group()
    forcelinkupdate_group.add_argument(
        "--forcelinkupdate",
        action="store_true",
        help="Update the links tables and do other secondary data updates",
    )
    forcelinkupdate_group.add_argument(
        "--forcerecursivelinkupdate",
        action="store_true",
        help=(
            "--forcelinkupdate plus update the links tables for any page that "
            "uses this page as a template."
        ),
    )
    parser.add_argument(
        "--redirects",
        action="store_true",
        help="Resolve redirects in page yielded by the generator.",
    )
    parsed_args = parser.parse_args(args=script_args)
    if not gen_factory.gens:
        pywikibot.error(
            "Unable to execute because no generator was defined. "
            "Use --help for further information."
        )
        return 1
    gen = gen_factory.getCombinedGenerator()
    site.login()
    PurgeBot(generator=gen, **vars(parsed_args)).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
