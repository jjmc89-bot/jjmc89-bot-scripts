#!/usr/bin/env python3
"""
This script fixes double (or more) category redirects.

The following parameters are supported:

-always           Don't prompt to save changes.

-summary          Specify an edit aummary for the bot.

&params;
"""
# Author : JJMC89
# License: MIT
from __future__ import annotations

from typing import Any, Iterable

import mwparserfromhell
import pywikibot
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp
from pywikibot.textlib import removeDisabledParts


docuReplacements = {  # noqa: N816 # pylint: disable=invalid-name
    "&params;": parameterHelp
}


def get_template_pages(
    templates: Iterable[pywikibot.Page],
) -> set[pywikibot.Page]:
    """
    Given an iterable of templates, return a set of pages.

    :param templates: iterable of templates
    """
    pages = set()
    for template in templates:
        if template.isRedirectPage():
            template = template.getRedirectTarget()
        if not template.exists():
            continue
        pages.add(template)
        for tpl in template.backlinks(filter_redirects=True):
            pages.add(tpl)
    return pages


class CategoryDoubleRedirectFixerBot(SingleSiteBot, ExistingPageBot):
    """Bot to fix double (or more) category redirects."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize."""
        self.available_options.update(  # pylint: disable=no-member
            {"summary": "Fix double redirect"}
        )
        super().__init__(**kwargs)
        self.templates = get_template_pages(
            [pywikibot.Page(self.site, "Category redirect", ns=10)]
        )

    def init_page(self, item: Any) -> pywikibot.Page:
        """Re-class the page."""
        page = super().init_page(item)
        try:
            return pywikibot.Category(page)
        except ValueError:
            return page

    def skip_page(self, page: pywikibot.Page) -> bool:
        """Sikp the page if it or its target are not category redirects."""
        if super().skip_page(page):
            return True
        if not isinstance(page, pywikibot.Category):
            pywikibot.error(f"{page!r} is not a category.")
            return True
        if not page.isCategoryRedirect():
            pywikibot.error(f"{page!r} is not a category redirect")
            return True
        target = page.getCategoryRedirectTarget()
        if not target.isCategoryRedirect():
            return True
        return False

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
        target = self.current_page.getCategoryRedirectTarget()
        seen = {self.current_page, target}
        while target.isCategoryRedirect():
            target = target.getCategoryRedirectTarget()
            if target in seen:
                pywikibot.error(
                    f"Skipping {self.current_page!r} due to possible circular"
                    f" redirect at {target!r}."
                )
                return
            seen.add(target)
        wikicode = mwparserfromhell.parse(
            self.current_page.text, skip_style_tags=True
        )
        for tpl in wikicode.ifilter_templates():
            try:
                template = pywikibot.Page(
                    self.site,
                    removeDisabledParts(str(tpl.name), site=self.site),
                    ns=10,
                )
                template.title()
            except pywikibot.exceptions.InvalidTitleError:
                continue
            if template in self.templates:
                tpl.add("1", target.title(with_ns=False))
                break
        self.put_current(str(wikicode), summary=self.opt.summary)


def main(*args: str) -> None:
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
        if arg == "summary":
            if not value:
                value = pywikibot.input(
                    f"Please enter a value for {arg}", default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    gen = gen_factory.getCombinedGenerator(preload=True)
    CategoryDoubleRedirectFixerBot(generator=gen, site=site, **options).run()


if __name__ == "__main__":
    main()
