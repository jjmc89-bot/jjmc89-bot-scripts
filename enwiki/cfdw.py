"""
This script processes Categories for discussion working pages.

&params;
"""
from __future__ import annotations

import re
from contextlib import suppress
from itertools import chain
from typing import Any, Generator, Iterable

import mwparserfromhell
import pywikibot
from mwparserfromhell.nodes import Node, Template, Text, Wikilink
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.page import PageSourceType
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp
from pywikibot.textlib import removeDisabledParts, replaceExcept
from pywikibot_extensions.page import Page
from typing_extensions import TypedDict


docuReplacements = {  # noqa: N816 # pylint: disable=invalid-name
    "&params;": parameterHelp
}
EXCEPTIONS = ("comment", "math", "nowiki", "pre", "source")
TEXTLINK_NAMESPACES = (118,)
TPL: dict[str, Iterable[str | pywikibot.Page]] = {
    "cat": ["c", "cl", "lc"],
    "cfd": [
        "Cfd full",
        "Cfm full",
        "Cfm-speedy full",
        "Cfr full",
        "Cfr-speedy full",
    ],
    "old cfd": ["Old CfD"],
}


class BotOptions(TypedDict, total=False):
    """Bot optsions."""

    old_cat: pywikibot.Category
    new_cats: list[pywikibot.Category]
    generator: Iterable[pywikibot.Page]
    site: pywikibot.site.BaseSite
    summary: str


class Instruction(TypedDict, total=False):
    """Instruction."""

    mode: str
    bot_options: BotOptions
    cfd_page: CfdPage
    action: str
    noredirect: bool
    redirect: bool
    result: str


class LineResults(TypedDict):
    """Line results."""

    cfd_page: CfdPage | None
    new_cats: list[pywikibot.Category]
    old_cat: pywikibot.Category | None
    prefix: str
    suffix: str


class CfdBot(SingleSiteBot, ExistingPageBot):
    """Bot to update categories."""

    update_options = {
        "always": True,
        "new_cats": [],
        "old_cat": None,
        "summary": None,
    }

    def __init__(self, **kwargs: Any) -> None:
        """Initialize."""
        super().__init__(**kwargs)
        self.opt.new_cats = sorted(self.opt.new_cats, reverse=True)

    def treat_wikilinks(self, text: str, textlinks: bool = False) -> str:
        """Process wikilinks."""
        cats = []
        old_cat_link = None
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for wikilink in wikicode.ifilter_wikilinks():
            if wikilink.title.strip().startswith(":") != textlinks:
                continue
            try:
                link_page = Page.from_wikilink(wikilink, self.site)
                link_cat = pywikibot.Category(link_page)
            except (ValueError, pywikibot.exceptions.Error):
                continue
            cats.append(link_cat)
            if link_cat == self.opt.old_cat:
                old_cat_link = wikilink
        if not old_cat_link:
            pywikibot.log(
                f"Did not find {self.opt.old_cat!r} in {self.current_page!r}."
            )
            return text
        new_cats = self.opt.new_cats
        if len(new_cats) == 1 and new_cats[0] not in cats:
            # Update the title to keep the sort key.
            prefix = ":" if textlinks else ""
            old_cat_link.title = f"{prefix}{new_cats[0].title()}"
            text = str(wikicode)
        else:
            for cat in new_cats:
                if cat not in cats:
                    wikicode.insert_after(
                        old_cat_link,
                        f"\n{cat.title(as_link=True, textlink=textlinks)}",
                    )
            old_cat_regex = re.compile(
                rf"\n?{re.escape(str(old_cat_link))}", re.M
            )
            text = replaceExcept(
                str(wikicode), old_cat_regex, "", EXCEPTIONS, site=self.site
            )
        return text

    def treat_page(self) -> None:
        """Process one page."""
        text = self.treat_wikilinks(self.current_page.text)
        if self.current_page.namespace() in TEXTLINK_NAMESPACES:
            text = self.treat_wikilinks(text, textlinks=True)
        self.put_current(
            text,
            summary=self.opt.summary,
            asynchronous=False,
            nocreate=True,
        )


class CfdPage(Page):
    """Represents a CFD page."""

    def __init__(self, source: PageSourceType, title: str = "") -> None:
        """Initialize."""
        super().__init__(source, title)
        if not (
            self.title(with_ns=False).startswith("Categories for discussion/")
            and self.namespace() == 4
        ):
            raise ValueError(f"{self!r} is not a CFD page.")

    def find_discussion(self, category: pywikibot.Category) -> CfdPage:
        """
        Return the relevant discussion.

        :param category: The category being discussed
        """
        if self.section():
            return self
        text = removeDisabledParts(self.text, tags=EXCEPTIONS, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(levels=[4]):
            heading = section.filter_headings()[0]
            heading_title = heading.title.strip()
            for node in heading.title.ifilter():
                if not isinstance(node, Text):
                    # Don't use headings with anything other than text.
                    discussion = self
                    break
            else:
                discussion = self.__class__.from_wikilink(
                    f"{self.title()}#{heading_title}", self.site
                )
                if category.title() == heading_title:
                    return discussion
            # Split approximately into close, nom, and others.
            parts = str(section).split("(UTC)")
            if len(parts) < 3:
                continue
            # Parse the nom for category links.
            nom = mwparserfromhell.parse(parts[1], skip_style_tags=True)
            for node in nom.ifilter():
                page = cat_from_node(node, self.site)
                if page and category == page:
                    return discussion
        return self

    def get_result_action(
        self, category: pywikibot.Category
    ) -> tuple[str, str]:
        """
        Return the discussion result and action.

        :param category: The category being discussed
        """
        result = action = ""
        if not self.section():
            return result, action
        text = removeDisabledParts(self.text, tags=EXCEPTIONS, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(levels=[4]):
            heading = section.filter_headings()[0]
            if heading.title.strip() == self.section():
                break
        else:
            section = None  # Trick pylint.
            return result, action
        for line in str(section).splitlines():
            matches = re.findall(
                r"''The result of the discussion was:''\s+'''(.+?)'''", line
            )
            if matches:
                result = matches[0]
            line_wc = mwparserfromhell.parse(line, skip_style_tags=True)
            for node in line_wc.ifilter():
                page = cat_from_node(node, self.site)
                if page and category == page:
                    matches = re.findall(r"'''Propose (.+?)'''", line)
                    if matches:
                        action = matches[0]
                    break
        return result, action


class CFDWPage(Page):
    """Represents a CFDW page."""

    MODES = ("move", "merge", "empty", "retain")

    def __init__(self, source: PageSourceType, title: str = "") -> None:
        """Initialize."""
        super().__init__(source, title)
        if not (
            self.title(with_ns=False).startswith(
                "Categories for discussion/Working"
            )
            and self.namespace() == 4
        ):
            raise ValueError(f"{self!r} is not a CFDW page.")
        self.mode: str | None = None
        self.instructions: list[Instruction] = []

    def parse(self) -> None:
        """Parse the page."""
        text = removeDisabledParts(self.text, tags=EXCEPTIONS, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(flat=True, include_lead=False):
            heading = section.filter_headings()[0]
            section_title = str(heading.title).lower()
            for mode in self.MODES:
                if mode in section_title:
                    self.mode = mode
                    break
            else:
                continue
            try:
                self._parse_section(str(section))
            except (ValueError, pywikibot.exceptions.Error):
                pywikibot.exception(tb=True)
        self._check_run()

    def _parse_section(self, section: str) -> None:
        """Parse a section of a page."""
        cfd_page = None
        cfd_prefix = cfd_suffix = ""
        for line in section.splitlines():
            assert self.mode is not None  # for mypy
            instruction = Instruction(
                mode=self.mode,
                bot_options=BotOptions(),
            )
            line_results = self._parse_line(line)
            instruction["bot_options"]["old_cat"] = line_results["old_cat"]
            instruction["bot_options"]["new_cats"] = line_results["new_cats"]
            if line_results["cfd_page"]:
                cfd_prefix = line_results["prefix"]
                cfd_suffix = line_results["suffix"]
            cfd_page = line_results["cfd_page"] or cfd_page
            if not (cfd_page and instruction["bot_options"]["old_cat"]):
                continue
            prefix = f"{line_results['prefix']} {cfd_prefix}"
            suffix = line_results["suffix"] or cfd_suffix
            if "NO BOT" in prefix:
                pywikibot.log(f"Bot disabled for: {line}")
                continue
            cfd = cfd_page.find_discussion(line_results["old_cat"])
            instruction["cfd_page"] = cfd
            if self.mode == "merge":
                instruction["redirect"] = "REDIRECT" in prefix
            elif self.mode == "move":
                instruction["noredirect"] = "REDIRECT" not in prefix
            elif self.mode == "retain":
                nc_matches = re.findall(
                    r"\b(no consensus) (?:for|to) (\w+)\b", suffix, flags=re.I
                )
                not_matches = re.findall(
                    r"\b(not )(\w+)\b", suffix, flags=re.I
                )
                if nc_matches:
                    result, action = nc_matches[0]
                elif not_matches:
                    result = "".join(not_matches[0])
                    action = re.sub(r"ed$", "e", not_matches[0][1])
                elif "keep" in suffix.lower():
                    result = "keep"
                    action = "delete"
                else:
                    result, action = cfd.get_result_action(
                        instruction["bot_options"]["old_cat"]
                    )
                instruction["result"] = result
                instruction["action"] = action
            self.instructions.append(instruction)

    def _parse_line(self, line: str) -> LineResults:
        """Parse a line of wikitext."""
        results = LineResults(
            cfd_page=None,
            old_cat=None,
            new_cats=[],
            prefix="",
            suffix="",
        )
        link_found = False
        wikicode = mwparserfromhell.parse(line, skip_style_tags=True)
        nodes = wikicode.filter(recursive=False)
        for index, node in enumerate(nodes, start=1):
            if isinstance(node, Text):
                if not link_found:
                    results["prefix"] = str(node).strip()
                elif link_found and index == len(nodes):
                    results["suffix"] = str(node).strip()
            else:
                page = cat_from_node(node, self.site)
                if page:
                    link_found = True
                    if not results["old_cat"]:
                        results["old_cat"] = page
                    else:
                        results["new_cats"].append(page)
                elif isinstance(node, Wikilink):
                    link_found = True
                    page = CfdPage.from_wikilink(node, self.site)
                    results["cfd_page"] = page
        return results

    def _check_run(self) -> None:
        """Check and run the instructions."""
        instructions = []
        seen = set()
        skip = set()
        # Collect categories and skips.
        for instruction in self.instructions:
            if instruction in instructions:
                # Remove duplicate.
                continue
            instructions.append(instruction)
            old_cat = instruction["bot_options"]["old_cat"]
            if old_cat in seen:
                skip.add(old_cat)
            seen.add(old_cat)
            for new_cat in instruction["bot_options"]["new_cats"]:
                seen.add(new_cat)
        # Only action instructions that shouldn't be skipped.
        self.instructions = []
        for instruction in instructions:
            old_cat = instruction["bot_options"]["old_cat"]
            cats = {old_cat}
            cats.update(instruction["bot_options"]["new_cats"])
            if cats & skip:
                pywikibot.warning(
                    f"{old_cat!r} is involved in multiple instructions. "
                    f"Skipping: {instruction!r}."
                )
            elif check_instruction(instruction):
                self.instructions.append(instruction)
                do_instruction(instruction)


def add_old_cfd(
    page: pywikibot.Page,
    cfd_page: CfdPage,
    action: str,
    result: str,
    summary: str,
) -> None:
    """Add {{Old CfD}} to the talk page."""
    date = cfd_page.title(with_section=False).rpartition("/")[2]
    wikicode = mwparserfromhell.parse(page.text, skip_style_tags=True)
    for tpl in wikicode.ifilter_templates():
        try:
            template = Page.from_wikilink(tpl.name, page.site, 10)
            if template not in TPL["old cfd"] or not tpl.has(
                "date", ignore_empty=True
            ):
                continue
        except pywikibot.exceptions.InvalidTitleError:
            continue
        if tpl.get("date").value.strip() == date:
            # Template already present.
            return
    wikicode.insert(0, "\n")
    old_cfd = Template("Old CfD")
    old_cfd.add("action", action)
    old_cfd.add("date", date)
    old_cfd.add("section", cfd_page.section())
    old_cfd.add("result", result)
    wikicode.insert(0, old_cfd)
    page.text = str(wikicode)
    page.save(summary=summary)


def cat_from_node(
    node: Node, site: pywikibot.site.BaseSite
) -> pywikibot.Category | None:
    """
    Return the category from the node.

    :param node: Node to get a category from
    :param site: Site the wikicode is on
    """
    with suppress(
        ValueError,
        pywikibot.exceptions.InvalidTitleError,
        pywikibot.exceptions.SiteDefinitionError,
    ):
        if isinstance(node, Template):
            tpl = Page.from_wikilink(node.name, site, 10)
            if tpl in TPL["cat"] and node.has("1"):
                title = node.get("1").strip()
                page = Page.from_wikilink(title, site, 14)
                return pywikibot.Category(page)
        elif isinstance(node, Wikilink):
            title = str(node.title).split("#", maxsplit=1)[0]
            page = Page.from_wikilink(title, site)
            return pywikibot.Category(page)
    return None


def check_instruction(instruction: Instruction) -> bool:
    """Check if the instruction can be performeed."""
    bot_options = instruction["bot_options"]
    old_cat = bot_options["old_cat"]
    new_cats = bot_options["new_cats"]
    if old_cat in new_cats:
        pywikibot.error(f"{old_cat!r} is also a {instruction['mode']} target.")
        return False
    if instruction["mode"] == "empty":
        if new_cats:
            pywikibot.error(f"empty mode has new categories for {old_cat!r}.")
            return False
    elif instruction["mode"] == "merge":
        if not new_cats:
            pywikibot.error(
                f"merge mode has no new categories for {old_cat!r}."
            )
            return False
        for new_cat in new_cats:
            if not new_cat.exists():
                pywikibot.error(f"{new_cat!r} does not exist.")
                return False
            if new_cat.isCategoryRedirect() or new_cat.isRedirectPage():
                pywikibot.error(f"{new_cat!r} is a redirect.")
                return False
    elif instruction["mode"] == "move":
        if len(new_cats) != 1:
            pywikibot.error(f"move mode has {len(new_cats)} new categories.")
            return False
        new_cat = new_cats[0]
        if (
            new_cat.exists()
            and old_cat.exists()
            and not old_cat.isCategoryRedirect()
        ):
            pywikibot.error(f"{new_cat!r} already exists.")
            return False
        if (
            old_cat.isCategoryRedirect() or old_cat.isRedirectPage()
        ) and not new_cat.exists():
            pywikibot.error(f"No target for move to {new_cats[0]!r}.")
            return False
        if new_cat.isCategoryRedirect() or new_cat.isRedirectPage():
            pywikibot.error(f"{new_cat!r} is a redirect.")
            return False
    elif instruction["mode"] == "retain":
        if not old_cat.exists():
            pywikibot.error(f"{old_cat!r} does not exist.")
            return False
        if new_cats:
            pywikibot.error(f"retain mode has new categories for {old_cat!r}.")
            return False
        if not instruction["action"] or not instruction["result"]:
            pywikibot.error(f"Missing action or result for {old_cat!r}.")
            return False
    else:
        pywikibot.error(f"Unknown mode: {instruction['mode']}.")
        return False
    return True


def delete_page(page: pywikibot.Page, summary: str) -> None:
    """Delete the page and dependent pages."""
    page.delete(
        reason=summary,
        prompt=False,
        deletetalk=page.toggleTalkPage().exists(),
    )
    if page.exists():
        return
    for redirect in page.redirects():
        redirect.delete(
            reason=(
                "[[WP:G8|G8]]: Redirect to deleted page "
                f"{page.title(as_link=True)}"
            ),
            prompt=False,
            deletetalk=redirect.toggleTalkPage().exists(),
        )


def do_instruction(instruction: Instruction) -> None:
    """Perform the instruction."""
    cfd_page = instruction["cfd_page"]
    bot_options = instruction["bot_options"]
    old_cat = bot_options["old_cat"]
    gen = chain(
        old_cat.members(), old_cat.backlinks(namespaces=TEXTLINK_NAMESPACES)
    )
    bot_options["generator"] = doc_page_add_generator(gen)
    bot_options["site"] = cfd_page.site
    cfd_link = cfd_page.title(as_link=True)
    if instruction["mode"] == "empty":
        bot_options["summary"] = (
            f"Removing {old_cat.title(as_link=True, textlink=True)} per "
            f"{cfd_link}"
        )
        CfdBot(**bot_options).run()
        # Wait for the category to be registered as empty.
        pywikibot.sleep(pywikibot.config.put_throttle)
        if old_cat.exists() and old_cat.isEmptyCategory():
            delete_page(old_cat, cfd_link)
    elif instruction["mode"] == "merge":
        redirect = False
        n_new_cats = len(bot_options["new_cats"])
        if n_new_cats == 1:
            new_cats = bot_options["new_cats"][0].title(
                as_link=True, textlink=True
            )
            redirect = instruction["redirect"]
        elif n_new_cats == 2:
            new_cats = " and ".join(
                cat.title(as_link=True, textlink=True)
                for cat in bot_options["new_cats"]
            )
        else:
            new_cats = f"{n_new_cats} categories"
        bot_options["summary"] = (
            f"Merging {old_cat.title(as_link=True, textlink=True)} to "
            f"{new_cats} per {cfd_link}"
        )
        CfdBot(**bot_options).run()
        # Wait for the category to be registered as empty.
        pywikibot.sleep(pywikibot.config.put_throttle)
        if (
            old_cat.exists()
            and old_cat.isEmptyCategory()
            and not old_cat.isCategoryRedirect()
        ):
            if redirect:
                redirect_cat(
                    old_cat,
                    bot_options["new_cats"][0],
                    f"Merged to {new_cats} per {cfd_link}",
                )
            else:
                delete_page(old_cat, cfd_link)
    elif instruction["mode"] == "move":
        with suppress(pywikibot.exceptions.Error):
            old_cat.move(
                bot_options["new_cats"][0].title(),
                reason=cfd_link,
                noredirect=instruction["noredirect"],
            )
            remove_cfd_tpl(bot_options["new_cats"][0], "Category moved")
        bot_options["summary"] = (
            f"Moving {old_cat.title(as_link=True, textlink=True)} to "
            f"{bot_options['new_cats'][0].title(as_link=True, textlink=True)}"
            f" per {cfd_link}"
        )
        CfdBot(**bot_options).run()
    elif instruction["mode"] == "retain":
        summary = f"{cfd_link} closed as {instruction['result']}"
        remove_cfd_tpl(old_cat, summary)
        add_old_cfd(
            old_cat.toggleTalkPage(),
            cfd_page,
            instruction["action"],
            instruction["result"],
            summary,
        )


def doc_page_add_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """
    Add documentation subpages for pages from another generator.

    :param generator: Pages to iterate over
    """
    for page in generator:
        yield page
        if not page.namespace().subpages:
            continue
        for subpage in page.site.doc_subpage:
            doc_page = pywikibot.Page(page.site, f"{page.title()}{subpage}")
            if doc_page.exists():
                yield doc_page


def get_template_pages(
    templates: Iterable[pywikibot.Page],
) -> set[pywikibot.Page]:
    """Given an iterable of templates, return a set of pages."""
    pages = set()
    for template in templates:
        if template.isRedirectPage():
            template = template.getRedirectTarget()
        if not template.exists():
            continue
        pages.add(template)
        for tpl in template.redirects():
            pages.add(tpl)
    return pages


def redirect_cat(
    cat: pywikibot.Category, target: pywikibot.Category, summary: str
) -> None:
    """
    Redirect a category to another category.

    :param cat: Category to redirect
    :param target: Category redirect target
    :param summary: Edit summary
    """
    tpl = Template("Category redirect")
    tpl.add("1", target.title(with_ns=False))
    cat.text = str(tpl)
    cat.save(summary=summary)


def remove_cfd_tpl(page: pywikibot.Page, summary: str) -> None:
    """
    Remove the CfD template from the page.

    :param page: Page to edit
    :param summary: Edit summary
    """
    text = re.sub(
        r"<!--\s*BEGIN CFD TEMPLATE\s*-->.*?"
        r"<!--\s*END CFD TEMPLATE\s*-->\n*",
        "",
        page.get(force=True),
        flags=re.I | re.M | re.S,
    )
    wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
    for tpl in wikicode.ifilter_templates():
        try:
            template = Page.from_wikilink(tpl.name, page.site, 10)
            if template in TPL["cfd"]:
                wikicode.remove(tpl)
        except pywikibot.exceptions.InvalidTitleError:
            continue
    page.text = str(wikicode).strip()
    page.save(summary=summary)


def main(*args: str) -> int:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    gen_factory.handle_args(local_args)
    for key, value in TPL.items():
        TPL[key] = get_template_pages(
            [pywikibot.Page(site, tpl, ns=10) for tpl in value]
        )
    for page in gen_factory.getCombinedGenerator():
        page = CFDWPage(page)
        if page.protection().get("edit", ("", ""))[0] == "sysop":
            page.parse()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
