#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script fixes double (or more) category redirects.

The following parameters are supported:

-always           Don't prompt to save changes.

-summary          Specify an edit aummary for the bot.

&params;
"""
# Author : JJMC89
# License: MIT
import mwparserfromhell
import pywikibot
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.pagegenerators import GeneratorFactory, parameterHelp
from pywikibot.textlib import removeDisabledParts


docuReplacements = {'&params;': parameterHelp}  # pylint: disable=invalid-name


def get_template_pages(templates):
    """
    Given an iterable of templates, return a set of pages.

    @param templates: iterable of templates (L{pywikibot.Page})
    @type templates: iterable

    @rtype: set
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

    def __init__(self, generator, **kwargs):
        """
        Initializer.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({'summary': 'Fix double redirect'})
        self.generator = generator
        super().__init__(**kwargs)
        self.templates = get_template_pages(
            [pywikibot.Page(self.site, 'Category redirect', ns=10)]
        )

    def init_page(self, item):
        """Re-class the page."""
        page = super().init_page(item)
        try:
            return pywikibot.Category(page)
        except ValueError:
            return page

    def skip_page(self, page):
        """Sikp the page if it or its target are not category redirects."""
        if super().skip_page(page):
            return True
        if not isinstance(page, pywikibot.Category):
            pywikibot.error('{} is not a category.'.format(page))
            return True
        if not page.isCategoryRedirect():
            pywikibot.error('{} is not a category redirect'.format(page))
            return True
        target = page.getCategoryRedirectTarget()
        if not target.isCategoryRedirect():
            return True
        return False

    def check_disabled(self):
        """Check if the task is disabled. If so, quit."""
        if not self.site.logged_in():
            self.site.login()
        page = pywikibot.Page(
            self.site,
            'User:{username}/shutoff/{class_name}.json'.format(
                username=self.site.user(), class_name=self.__class__.__name__
            ),
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                e = '{} disabled:\n{}'.format(self.__class__.__name__, content)
                pywikibot.error(e)
                self.quit()

    def treat_page(self):
        """Process one page."""
        self.check_disabled()
        target = self.current_page.getCategoryRedirectTarget()
        seen = {self.current_page, target}
        while target.isCategoryRedirect():
            target = target.getCategoryRedirectTarget()
            if target in seen:
                pywikibot.error(
                    'Skipping {} due to possible circular redirect at {}.'
                    .format(self.current_page, target)
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
            except pywikibot.InvalidTitle:
                continue
            if template in self.templates:
                tpl.add('1', target.title(with_ns=False))
                break
        self.put_current(str(wikicode), summary=self.getOption('summary'))


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = GeneratorFactory(site)
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg == 'summary':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for {}'.format(arg), default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    gen = gen_factory.getCombinedGenerator(preload=True)
    CategoryDoubleRedirectFixerBot(gen, site=site, **options).run()


if __name__ == '__main__':
    main()
