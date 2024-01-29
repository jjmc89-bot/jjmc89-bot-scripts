"""
This script deploys editnotices.

The following parameters are required:

-editnotice_template Title of the editnotice template

The following parameters are supported:

-always           Don't prompt to save changes.

-subject_only     Restrict to subject pages

-talk_only        Restrict to talk pages

-to_subject       Add each talk page's subject page

-to_talk          Add each subject page's talk page

&params;
"""

from __future__ import annotations

from collections.abc import Generator, Iterable
from typing import Any

import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import CurrentPageBot, SingleSiteBot
from pywikibot_extensions.page import Page


docuReplacements = {"&params;": pagegenerators.parameterHelp}  # noqa: N816


def validate_options(
    options: dict[str, Any], site: pywikibot.site.APISite
) -> bool:
    """
    Validate the options and return bool.

    :param options: options to validate
    """
    pywikibot.log("Options:")
    required_keys = ["editnotice_template"]
    has_keys = []
    for key, value in options.items():
        pywikibot.log(f"-{key} = {value}")
        if key in required_keys:
            has_keys.append(key)
        if key == "editnotice_template":
            if not isinstance(key, str):
                return False
            options[key] = "{{" + value + "}}"
            editnotice_page = Page(site, value, ns=10)
            if not editnotice_page.exists():
                return False
    if sorted(has_keys) != sorted(required_keys):
        return False
    options["editnotice_page"] = editnotice_page
    return True


def page_with_subject_page_generator(
    generator: Iterable[pywikibot.Page],
    return_subject_only: bool = False,
) -> Generator[pywikibot.Page, None, None]:
    """
    Yield pages and associated subject pages from another generator.

    Only yields subject pages if the original generator yields a non-
    subject page, and does not check if the subject page in fact exists.
    """
    for page in generator:
        if not return_subject_only or not page.isTalkPage():
            yield page
        if page.isTalkPage():
            yield page.toggleTalkPage()


def subject_page_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """Yield subject pages from another generator."""
    for page in generator:
        if not page.isTalkPage():
            yield page


def talk_page_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """Yield talk pages from another generator."""
    for page in generator:
        if page.isTalkPage():
            yield page


def editnotice_page_generator(
    generator: Iterable[pywikibot.Page],
) -> Generator[pywikibot.Page, None, None]:
    """
    Yield editnotice pages from another generator.

    Only for existing, non-redirect pages in the other generator
    """
    for page in generator:
        if page.exists() and not page.isRedirectPage():
            title = page.title(with_section=False)
            editnotice_title = f"Template:Editnotices/Page/{title}"
            editnotice_page = Page(page.site, editnotice_title)
            yield editnotice_page


class EditnoticeDeployer(SingleSiteBot, CurrentPageBot):
    """Bot to deploy editnotices."""

    update_options = {
        "always": False,
        "editnotice_page": None,
        "editnotice_template": None,
    }

    def skip_page(self, page: pywikibot.Page) -> bool:
        """
        Skip pages that meet either condition.

            1) already has the editnotice
            2) non-exitent with deleted revisions
        """
        if Page(page).has_template([self.opt.editnotice_page]):
            return True
        if not page.exists() and page.has_deleted_revisions():
            pywikibot.warning(f"{page!r} has deleted revisions. Skipping.")
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
        if self.current_page.isRedirectPage():
            text = ""
        else:
            text = self.current_page.text
        self.put_current(
            "\n".join((self.opt.editnotice_template, text)),
            summary="Deploying editnotice: " + self.opt.editnotice_template,
            minor=False,
        )


def main(*args: str) -> int:
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    """
    options = {
        "subject_only": False,
        "talk_only": False,
        "to_subject": False,
        "to_talk": False,
    }
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = pagegenerators.GeneratorFactory(site)
    script_args = gen_factory.handle_args(local_args)
    for arg in script_args:
        arg, _, value = arg.partition(":")
        arg = arg[1:]
        if arg == "editnotice_template":
            if not value:
                value = pywikibot.input(
                    f"Please enter a value for {arg}", default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if not validate_options(options, site):
        pywikibot.error("Invalid options.")
        return 1
    gen = gen_factory.getCombinedGenerator()
    if options["to_subject"]:
        gen = page_with_subject_page_generator(
            gen, return_subject_only=options["subject_only"]
        )
    elif options["to_talk"]:
        gen = pagegenerators.PageWithTalkPageGenerator(
            gen, return_talk_only=options["talk_only"]
        )
    elif options["subject_only"]:
        gen = subject_page_generator(gen)
    elif options["talk_only"]:
        gen = talk_page_generator(gen)
    gen = editnotice_page_generator(gen)
    for key in ("subject_only", "talk_only", "to_subject", "to_talk"):
        options.pop(key, None)
    gen = pagegenerators.PreloadingGenerator(gen)
    EditnoticeDeployer(generator=gen, site=site, **options).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
