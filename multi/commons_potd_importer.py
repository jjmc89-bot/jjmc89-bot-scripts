"""Update page with Wikimedia Commons picture of the day."""

from __future__ import annotations

import argparse
import re
from typing import Any

import mwparserfromhell
import pywikibot
from pywikibot.bot import _GLOBAL_HELP, ExistingPageBot, MultipleSitesBot
from pywikibot.pagegenerators import GeneratorFactory
from pywikibot_extensions.page import Page, get_redirects


class CommonsPotdImporter(MultipleSitesBot, ExistingPageBot):
    """Bot to import the Commons POTD with caption."""

    def __init__(self, **kwargs: Any) -> None:
        """Iniitialize."""
        super().__init__(**kwargs)
        self.commons = pywikibot.Site("commons", "commons")
        date = self.commons.server_time().date().isoformat()
        self.potd_title = f"Template:Potd/{date}"
        potd_tpl = pywikibot.Page(self.commons, self.potd_title)
        potd_fn_titles = [
            p.title(with_ns=False)
            for p in get_redirects(
                frozenset((Page(self.commons, "Template:Potd filename"),)),
                namespaces=10,
            )
        ]
        wikicode = mwparserfromhell.parse(potd_tpl.text, skip_style_tags=True)
        for tpl in wikicode.ifilter_templates():
            if tpl.name.matches(potd_fn_titles) and tpl.has(
                "1", ignore_empty=True
            ):
                self.potd = tpl.get("1").value.strip()
                break
        else:
            raise ValueError("Failed to find the POTD.")
        self.potd_desc_titles = [
            p.title(with_ns=False)
            for p in get_redirects(
                frozenset((Page(self.commons, "Template:Potd description"),)),
                namespaces=10,
            )
        ]
        repo = self.commons.data_repository()
        self.doc_item = pywikibot.ItemPage(repo, "Q4608595")

    def treat_page(self) -> None:
        """Process one page."""
        site = self.current_page.site
        doc_tpl = pywikibot.Page(site, self.doc_item.getSitelink(site))
        summary = "Updating Commons picture of the day, "
        caption = ""
        for lang in (site.lang, "en"):
            caption_title = f"{self.potd_title} ({lang})"
            caption_page = pywikibot.Page(self.commons, caption_title)
            if not caption_page.exists():
                continue
            wikicode = mwparserfromhell.parse(
                caption_page.text, skip_style_tags=True
            )
            for tpl in wikicode.ifilter_templates():
                if tpl.name.matches(self.potd_desc_titles) and tpl.has(
                    "1", ignore_empty=True
                ):
                    caption = tpl.get("1").value.strip()
            if caption:
                # Remove templates, etc.
                caption = self.commons.expand_text(caption)
                # Make all interwikilinks go through Commons.
                caption_wikicode = mwparserfromhell.parse(
                    caption, skip_style_tags=True
                )
                for wikilink in caption_wikicode.ifilter_wikilinks():
                    title = wikilink.title.strip()
                    prefix = ":c" + ("" if title.startswith(":") else ":")
                    wikilink.title = prefix + title
                summary += f"[[:c:{caption_title}|caption attribution]]"
                caption = str(caption_wikicode)
                break
        else:
            summary += "failed to get a caption"
        text = (
            "<includeonly>{{#switch:{{{1|}}}\n"
            f"|caption={caption}\n"
            f"|#default={self.potd}\n"
            "}}</includeonly><noinclude>"
            f"{{{{{doc_tpl.title(with_ns=False)}}}}}</noinclude>"
        )
        self.put_current(text, summary=summary, minor=False)


def main(*args: str) -> int:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    script_args = gen_factory.handle_args(local_args)
    parser = argparse.ArgumentParser(
        description=__doc__,
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
        "--always",
        action="store_true",
        help="do not prompt to save changes",
    )
    parsed_args = parser.parse_args(args=script_args)
    gen = gen_factory.getCombinedGenerator()
    CommonsPotdImporter(generator=gen, **vars(parsed_args)).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
