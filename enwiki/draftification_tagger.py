"""Tag draftified articles."""

from __future__ import annotations

import argparse
import re
from collections.abc import Generator
from typing import Any

import pywikibot
from pywikibot.bot import _GLOBAL_HELP, ExistingPageBot, SingleSiteBot
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp
from pywikibot_extensions.page import Page


class DfyTaggerBot(SingleSiteBot, ExistingPageBot):
    """Bot to tag draftified articles."""

    update_options = {
        "summary": "Add {{{{{tpl}}}}}",
        "template": "drafts moved from mainspace",
    }
    use_redirects = False

    def __init__(self, **kwargs: Any) -> None:
        """Initialize."""
        super().__init__(**kwargs)
        template = self.opt.template
        self.add_text = f"\n\n{{{{subst:{template}}}}}"
        self.summary = self.opt.summary.format(tpl=template)

    def skip_page(self, page: pywikibot.Page) -> bool:
        """Skip non-drafts and drafts with the template."""
        if page.namespace() != 118:
            pywikibot.warning(f"{page!r} is not a draft.")
            return True
        if Page(page).has_template(self.opt.template):
            pywikibot.warning(f"{page!r} already has the template.")
            return True
        return super().skip_page(page)

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
        self.put_current(
            self.current_page.text.strip() + self.add_text,
            summary=self.summary,
            nocreate=True,
        )


def draftified_page_generator(
    site: pywikibot.site.BaseSite,
    start: pywikibot.Timestamp | None,
) -> Generator[pywikibot.Page]:
    """
    Yield draftified pages based on page moves.

    :param site: site to yield page moves from
    """
    gen = site.logevents(
        logtype="move", namespace=0, start=start, reverse=True
    )
    for move in gen:
        if move.target_ns == 118:
            yield move.target_page


def main(*args: str) -> int:
    """Process command line arguments and invoke bot."""
    local_args = pywikibot.handle_args(args, do_help=False)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    script_args = gen_factory.handle_args(local_args)
    parser = argparse.ArgumentParser(
        description="Tag draftified articles",
        epilog=re.sub(
            r"\n\n?-help +.+?(\n\n-|\s*$)",
            r"\1",
            _GLOBAL_HELP + parameterHelp,
            flags=re.S,
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--always",
        "-a",
        action="store_true",
        help="Do not prompt to save changes",
    )
    parser.add_argument(
        "--start",
        type=pywikibot.Timestamp.fromISOformat,
        help="Timestamp to start from",
        metavar="%Y-%m-%dT%H:%M:%SZ",
    )
    parser.add_argument(
        "--summary", help="Edit aummary for the bot", default=argparse.SUPPRESS
    )
    parser.add_argument(
        "--template", help="Template to add", default=argparse.SUPPRESS
    )
    parsed_args = vars(parser.parse_args(args=script_args))
    start = parsed_args.pop("start")
    gen = None if gen_factory.gens else draftified_page_generator(site, start)
    gen = gen_factory.getCombinedGenerator(gen=gen)
    DfyTaggerBot(generator=gen, site=site, **parsed_args).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
