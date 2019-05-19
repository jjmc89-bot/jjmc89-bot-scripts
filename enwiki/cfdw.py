#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script processes Categories for discussion working pages.

&params;
"""
# Author : JJMC89
# License: MIT
import mwparserfromhell
from mwparserfromhell.nodes import Heading
import pywikibot
from pywikibot import pagegenerators
from pywikibot.textlib import removeDisabledParts
from scripts.category import CategoryMoveRobot #pylint: disable=import-error


docuReplacements = { #pylint: disable=invalid-name
    '&params;': pagegenerators.parameterHelp
}


class CfdPage(pywikibot.Page):
    """Represents a CFD page."""

    def __init__(self, source, title=''):
        """Initializer."""
        super().__init__(source, title)
        if (not self.title(with_ns=False).startswith(
                'Categories for discussion/') or self.namespace() != 4):
            raise ValueError('{} is not a CFD page.'.format(self))

    def find_discussion(self, category):
        """Find the section with the relevant discussion."""
        if self.section():
            return self.title(as_link=True)
        text = removeDisabledParts(self.text, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(levels=[4]):
            heading = section.filter(forcetype=Heading)[0]
            section_title = str(heading.title).strip()
            discussion = '[[{}#{}]]'.format(self.title(), section_title)
            if category.title() == section_title:
                return discussion
            # Split approximately into close, nom, and others
            parts = str(section).split('(UTC)')
            if len(parts) < 3:
                continue
            # Parse the nom for links
            for wikilink in pywikibot.link_regex.finditer(parts[1]):
                title = wikilink.group('title').strip().split('#')[0]
                if not title:
                    continue
                title = pywikibot.Page(self.site, title).title()
                if category.title() == title:
                    return discussion
        return self.title(as_link=True)


def parse_page(page):
    """Parse a CFD working page."""
    text = removeDisabledParts(page.text, site=page.site)
    wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
    for section in wikicode.get_sections(flat=True, include_lead=False):
        heading = section.filter(forcetype=Heading)[0]
        section_title = str(heading.title).lower()
        if 'move' in section_title:
            mode = 'move'
        elif 'empty' in section_title:
            mode = 'empty'
        else:
            continue
        parse_section(section, page.site, mode)


def parse_section(section, site, mode):
    """Parse a section of a CFD working page and invoke a bot."""
    cfd_page = None
    for line in str(section).splitlines():
        cfd_page, old_cat, new_cats = parse_line(line, site, cfd_page)
        if not cfd_page or not old_cat or len(new_cats) > 1:
            continue
        new_cat = new_cats[0] if new_cats else None
        discussion = cfd_page.find_discussion(old_cat)
        if mode == 'empty':
            if new_cats:
                continue
            edit_summary = 'Removing {old_cat} per {cfd}'.format(
                old_cat=old_cat.title(as_link=True, textlink=True),
                cfd=discussion
            )
        else: # mode == 'move':
            if not new_cats:
                continue
            edit_summary = 'Moving {old_cat} to {new_cats} per {cfd}'.format(
                old_cat=old_cat.title(as_link=True, textlink=True),
                new_cats=new_cat.title(as_link=True, textlink=True),
                cfd=discussion
            )
        CategoryMoveRobot(oldcat=old_cat, newcat=new_cat, batch=True,
                          comment=edit_summary, inplace=True, move_oldcat=True,
                          deletion_comment=discussion, move_comment=discussion,
                          delete_oldcat=True).run()


def parse_line(line, site, cfd_page):
    """Parse a line of wikitext from a CFD working page."""
    old_cat = None
    new_cats = list()
    if 'NO BOT' in line:
        return cfd_page, old_cat, new_cats
    for wikilink in pywikibot.link_regex.finditer(line):
        title = wikilink.group('title').strip().split('#')[0]
        if not title:
            continue
        link = pywikibot.Page(site, title)
        if link.is_categorypage():
            link = pywikibot.Category(link)
            if not old_cat:
                old_cat = link
            elif link.isCategoryRedirect():
                old_cat = None
                break
            else:
                new_cats.append(link)
        else:
            try:
                cfd_page = CfdPage(link)
            except ValueError:
                old_cat = None
                break
    return cfd_page, old_cat, new_cats


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    gen_factory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        gen_factory.handleArg(arg)
    for page in gen_factory.getCombinedGenerator(preload=False):
        if page.protection().get('edit', ('', ''))[0] == 'sysop':
            parse_page(page)


if __name__ == '__main__':
    main()
