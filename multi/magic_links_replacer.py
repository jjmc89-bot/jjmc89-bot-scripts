"""
This script replaces magic links.

The following parameters are required:

-config_title     The page title that has the JSON config (object).

The following parameters are supported:

-always           Don't prompt to save changes.

&params;
"""
from __future__ import annotations

import json
import re
from re import Pattern
from typing import Any

import pywikibot
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp
from pywikibot.textlib import replaceExcept


docuReplacements = {"&params;": parameterHelp}  # noqa: N816
# For _create_regexes().
_regexes: dict[str, Pattern[str]] = {}


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


def validate_config(config: dict[str, Any]) -> bool:
    """
    Validate the config and return bool.

    :param config: config to validate
    """
    pywikibot.log("Config:")
    for key, value in config.items():
        pywikibot.log(f"-{key} = {value}")
        if key in ("ISBN", "PMID", "RFC", "summary"):
            if not isinstance(value, str):
                return False
            config[key] = value.strip() or None
        else:
            return False
    return True


def _create_regexes() -> None:
    """Fill (and possibly overwrite) _regexes with default regexes."""
    space = r"(?:[^\S\n]|&nbsp;|&\#0*160;|&\#[Xx]0*[Aa]0;)"
    spaces = rf"{space}+"
    space_dash = rf"(?:-|{space})"
    tags = [
        "gallery",
        "math",
        "nowiki",
        "pre",
        "score",
        "source",
        "syntaxhighlight",
    ]
    # Based on pywikibot.textlib.compileLinkR
    # and https://gist.github.com/gruber/249502
    url = r"""(?:[a-z][\w-]+://[^\]\s<>"]*[^\]\s\.:;,<>"\|\)`!{}'?«»“”‘’])"""
    _regexes.update(
        {
            "bare_url": re.compile(rf"\b({url})", flags=re.I),
            "bracket_url": re.compile(rf"(\[{url}[^\]]*\])", flags=re.I),
            "ISBN": re.compile(
                rf"\bISBN(?P<separator>{spaces})(?P<value>(?:97[89]"
                rf"{space_dash}?)?(?:[0-9]{space_dash}?){{9}}[0-9Xx])\b"
            ),
            "PMID": re.compile(
                rf"\bPMID(?P<separator>{spaces})(?P<value>[0-9]+)\b"
            ),
            "RFC": re.compile(
                rf"\bRFC(?P<separator>{spaces})(?P<value>[0-9]+)\b"
            ),
            "tags": re.compile(
                r"""(<\/?\w+(?:\s+\w+(?:\s*=\s*(?:(?:"[^"]*")|(?:'[^']*')|"""
                r"""[^>\s]+))?)*\s*\/?>)"""
            ),
            "tags_content": re.compile(
                rf"(<(?P<tag>{r'|'.join(tags)})\b.*?</(?P=tag)>)",
                flags=re.I | re.M,
            ),
        }
    )


def split_into_sections(text: str) -> list[str]:
    """
    Split wikitext into sections based on any level wiki heading.

    :param text: Text to split
    """
    headings_regex = re.compile(
        r"^={1,6}.*?={1,6}(?: *<!--.*?-->)?\s*$", flags=re.M
    )
    sections = []
    last_match_start = 0
    for match in headings_regex.finditer(text):
        match_start = match.start()
        if match_start > 0:
            sections.append(text[last_match_start:match_start])
            last_match_start = match_start
    sections.append(text[last_match_start:])
    return sections


class MagicLinksReplacer(SingleSiteBot, ExistingPageBot):
    """Bot to replace magic links."""

    update_options = {"summary": None, "ISBN": None, "PMID": None, "RFC": None}
    use_redirects = False

    def __init__(self, **kwargs: Any) -> None:
        """Initialize."""
        super().__init__(**kwargs)
        _create_regexes()
        self.replace_exceptions: list[Pattern[str] | str] = [
            _regexes[key]
            for key in ("bare_url", "bracket_url", "tags_content", "tags")
        ]
        self.replace_exceptions += [
            "category",
            "comment",
            "file",
            "interwiki",
            "invoke",
            "link",
            "property",
            "template",
        ]

    def check_disabled(self) -> None:
        """Check if the task is disabled. If so, quit."""
        class_name = self.__class__.__name__
        page = pywikibot.Page(
            self.site,
            f"User:{self.site.username()}/shutoff/{class_name}",
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                pywikibot.error(f"{class_name} disabled:\n{content}")
                self.quit()

    def treat_page(self) -> None:
        """Process one page."""
        self.check_disabled()
        text = ""
        for section in split_into_sections(self.current_page.text):
            for identifier in ("ISBN", "PMID", "RFC"):
                if self.opt[identifier]:
                    section = replaceExcept(
                        section,
                        _regexes[identifier],
                        self.opt[identifier],
                        self.replace_exceptions,
                        site=self.site,
                    )
            text += section
        self.put_current(text, summary=self.opt.summary)


def main(*args: str) -> int:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    script_args = gen_factory.handle_args(local_args)
    for arg in script_args:
        arg, _, value = arg.partition(":")
        arg = arg[1:]
        if arg == "config_title":
            if not value:
                value = pywikibot.input(
                    f"Please enter a value for {arg}", default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    gen = gen_factory.getCombinedGenerator(preload=True)
    if "config_title" not in options:
        pywikibot.bot.suggest_help(missing_parameters=["config_title"])
        return 1
    config = get_json_from_page(
        pywikibot.Page(site, options.pop("config_title"))
    )
    if validate_config(config):
        options.update(config)
    else:
        pywikibot.error("Invalid config.")
        return 1
    MagicLinksReplacer(generator=gen, site=site, **options).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
