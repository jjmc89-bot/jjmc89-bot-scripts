#!/usr/bin/env python3
"""Tag draftified articles."""
# Author : JJMC89
# License: MIT
import argparse
import re
from typing import Any, Dict, FrozenSet, Generator, Iterable, Optional, Union

import pywikibot
from pywikibot.bot import (
    _GLOBAL_HELP,
    ExistingPageBot,
    NoRedirectPageBot,
    SingleSiteBot,
)
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp


# Cache for get_redirects().
_redirects_cache = (
    dict()
)  # type: Dict[FrozenSet[pywikibot.Page], FrozenSet[pywikibot.Page]]


def get_redirects(
    pages: Iterable[pywikibot.Page],
) -> FrozenSet[pywikibot.Page]:
    """Given pages, return all possible titles."""
    pages = frozenset(pages)
    if pages not in _redirects_cache:
        link_pages = set()
        for page in pages:
            while page.isRedirectPage():
                try:
                    page = page.getRedirectTarget()
                except pywikibot.CircularRedirect:
                    break
            if not page.exists():
                continue
            link_pages.add(page)
            for redirect in page.backlinks(filter_redirects=True):
                link_pages.add(redirect)
        _redirects_cache[pages] = frozenset(link_pages)
    return _redirects_cache[pages]


def has_template(
    page: pywikibot.Page,
    templates: Union[str, Iterable[Union[pywikibot.Page, str]]],
) -> bool:
    """
    Return True if the page has one of the templates. False otherwise.

    @param page: page to check
    @param templates: templates to check
    """
    if isinstance(templates, str):
        templates = [templates]
    templates = get_redirects(
        tpl
        if isinstance(tpl, pywikibot.Page)
        else pywikibot.Page(page.site, tpl, ns=10)
        for tpl in templates
    )
    return bool(templates & set(page.templates()))


class DfyTaggerBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    """Bot to tag draftified articles."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize."""
        self.available_options.update(  # pylint: disable=no-member
            {
                'summary': 'Add {{{{{tpl}}}}}',
                'template': 'drafts moved from mainspace',
            }
        )
        super().__init__(**kwargs)
        template = self.opt.template
        self.add_text = '\n\n{{{{subst:{tpl}}}}}'.format(tpl=template)
        self.summary = self.opt.summary.format(tpl=template)

    def skip_page(self, page: pywikibot.Page) -> bool:
        """Skip non-drafts and drafts with the template."""
        if page.namespace() != 118:
            pywikibot.warning('{} is not a draft.'.format(page))
            return True
        if has_template(page, self.opt.template):
            pywikibot.warning('{} already has the template.'.format(page))
            return True
        return super().skip_page(page)

    def check_disabled(self) -> None:
        """Check if the task is disabled. If so, quit."""
        class_name = self.__class__.__name__
        page = pywikibot.Page(
            self.site,
            'User:{}/shutoff/{}.json'.format(self.site.username(), class_name),
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                pywikibot.error('{} disabled:\n{}'.format(class_name, content))
                self.quit()

    def treat_page(self) -> None:
        """Process one page."""
        self.check_disabled()
        self.put_current(
            self.current_page.text.strip() + self.add_text,
            summary=self.summary,
        )


def draftified_page_generator(
    site: pywikibot.site.BaseSite, start: Optional[pywikibot.Timestamp],
) -> Generator[pywikibot.Page, None, None]:
    """
    Yield draftified pages based on page moves.

    @param site: site to yield page moves from
    """
    gen = site.logevents(
        logtype='move', namespace=0, start=start, reverse=True
    )
    for move in gen:
        if move.target_ns == 118:
            yield move.target_page


def main(*args: str) -> None:
    """Process command line arguments and invoke bot."""
    local_args = pywikibot.handle_args(args, do_help=False)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    script_args = [arg for arg in local_args if not gen_factory.handleArg(arg)]
    parser = argparse.ArgumentParser(
        description='Tag draftified articles',
        epilog=re.sub(
            r'\n\n?-help +.+?(\n\n-|\s*$)',
            r'\1',
            _GLOBAL_HELP + parameterHelp,
            flags=re.S,
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        '--always',
        '-a',
        action='store_true',
        help='Do not prompt to save changes',
    )
    parser.add_argument(
        '--start',
        type=pywikibot.Timestamp.fromISOformat,
        help='Timestamp to start from',
        metavar='%Y-%m-%dT%H:%M:%SZ',
    )
    parser.add_argument(
        '--summary', help='Edit aummary for the bot', default=argparse.SUPPRESS
    )
    parser.add_argument(
        '--template', help='Template to add', default=argparse.SUPPRESS
    )
    parsed_args = vars(parser.parse_args(args=script_args))
    start = parsed_args.pop('start')
    gen = None if gen_factory.gens else draftified_page_generator(site, start)
    gen = gen_factory.getCombinedGenerator(gen=gen)
    DfyTaggerBot(generator=gen, site=site, **parsed_args).run()


if __name__ == '__main__':
    main()
