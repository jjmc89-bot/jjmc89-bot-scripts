#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
This script processes Categories for discussion working pages.

&params;
"""
# Author : JJMC89
# License: MIT
import re
import mwparserfromhell
from mwparserfromhell.nodes import Heading, Template, Text, Wikilink
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import ExistingPageBot, SingleSiteBot
from pywikibot.textlib import removeDisabledParts, replaceExcept


docuReplacements = { #pylint: disable=invalid-name
    '&params;': pagegenerators.parameterHelp
}
SUMMARIES = {
    'redirect': '[[WP:G8|G8]]: Redirect to deleted page {}',
    'talk': '[[WP:G8|G8]]: Talk page of deleted page {}'
}
TPL = {
    'cat': ['c', 'cl', 'lc'],
    'cfd': ['Cfd full', 'Cfm full', 'Cfm-speedy full', 'Cfr full',
            'Cfr-speedy full'],
    'old cfd': ['Old CfD']
}


class CfdBot(SingleSiteBot, ExistingPageBot):
    """Bot to update categories."""

    EXCEPTIONS = ['comment', 'math', 'nowiki', 'pre', 'source']

    def __init__(self, generator, **kwargs):
        """
        Initializer.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'always': True,
            'new_cats': list(),
            'old_cat': None,
            'summary': None
        })
        self.generator = generator
        super().__init__(**kwargs)
        self.options['new_cats'] = sorted(self.getOption('new_cats'),
                                          reverse=True)

    def treat_page(self):
        """Process one page."""
        cats = list()
        old_cat_link = None
        wikicode = mwparserfromhell.parse(self.current_page.text,
                                          skip_style_tags=True)
        for link in wikicode.ifilter(forcetype=Wikilink):
            if link.title.strip().startswith(':'):
                continue
            try:
                link_page = pywikibot.Page(self.site, str(link.title))
                link_cat = pywikibot.Category(link_page)
            except (ValueError, pywikibot.Error):
                continue
            cats.append(link_cat)
            if link_cat == self.getOption('old_cat'):
                old_cat_link = link
        if not old_cat_link:
            pywikibot.log('Did not find {} in {}.'.format(
                self.getOption('old_cat'), self.current_page))
            return
        new_cats = self.getOption('new_cats')
        if len(new_cats) == 1 and new_cats[0] not in cats:
            # Update the title to keep the sort key.
            old_cat_link.title = new_cats[0].title()
            text = str(wikicode)
        else:
            for cat in new_cats:
                if cat not in cats:
                    wikicode.insert_after(old_cat_link, '\n' + cat.aslink())
            old_cat_regex = re.compile(r'\n?' + re.escape(str(old_cat_link)),
                                       re.M)
            text = replaceExcept(str(wikicode), old_cat_regex, '',
                                 self.EXCEPTIONS, site=self.site)
        self.put_current(text, summary=self.getOption('summary'),
                         asynchronous=False, nocreate=True)


class CfdPage(pywikibot.Page):
    """Represents a CFD page."""

    def __init__(self, source, title=''):
        """Initializer."""
        super().__init__(source, title)
        if (not self.title(with_ns=False).startswith(
                'Categories for discussion/') or self.namespace() != 4):
            raise ValueError('{} is not a CFD page.'.format(self))

    def _cat_from_node(self, node):
        """
        Return the category from the node.

        @param node: Node to get a category from
        @type node: mwparserfromhell.Node
        @rtype: L{pywikibot.Category} or None
        """
        if isinstance(node, Template):
            tpl = pywikibot.Page(self.site, str(node.name), ns=10)
            if tpl in TPL['cat'] and node.has('1'):
                title = node.get('1').strip()
                return pywikibot.Category(self.site, title)
        elif isinstance(node, Wikilink):
            title = str(node.title).split('#')[0]
            try:
                page = pywikibot.Page(self.site, title)
                if page.namespace() == 14:
                    return pywikibot.Category(page)
            except pywikibot.SiteDefinitionError:
                # Ignore unknown sites.
                pass
        return None

    def find_discussion(self, category):
        """
        Return the relevant discussion.

        @param category: The category being discussed
        @type category: L{pywikibot.Category}
        @rtype: CfdPage
        """
        if self.section():
            return self
        text = removeDisabledParts(self.text, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(levels=[4]):
            heading = section.filter(forcetype=Heading)[0]
            section_title = str(heading.title).strip()
            discussion = self.__class__(
                self.site,
                '{}#{}'.format(self.title(), section_title)
            )
            if category.title() == section_title:
                return discussion
            # Split approximately into close, nom, and others.
            parts = str(section).split('(UTC)')
            if len(parts) < 3:
                continue
            # Parse the nom for category links.
            nom = mwparserfromhell.parse(parts[1], skip_style_tags=True)
            for node in nom.ifilter():
                page = self._cat_from_node(node)
                if page and category == page:
                    return discussion
        return self

    def get_action(self, category):
        """
        Return the discussion action.

        @param category: The category being discussed
        @type category: L{pywikibot.Category}
        @rtype: str or None
        """
        if not self.section():
            return None
        text = removeDisabledParts(self.text, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(levels=[4]):
            heading = section.filter(forcetype=Heading)[0]
            if str(heading.title).strip() == self.section():
                break
        else:
            section = None # Trick pylint.
            return None
        # Parse the discussion for category links and action.
        for line in str(section).splitlines():
            found = False
            line_wc = mwparserfromhell.parse(line, skip_style_tags=True)
            for node in line_wc.ifilter():
                page = self._cat_from_node(node)
                if page and category == page:
                    found = True
                    break
            matches = re.findall(r"'''Propose (.+?)'''", line)
            if found and matches:
                return matches[0]
        return None

    def get_result(self):
        """
        Return the discussion result.

        @rtype: str or None
        """
        if not self.section():
            return None
        text = removeDisabledParts(self.text, site=self.site)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        for section in wikicode.get_sections(levels=[4]):
            heading = section.filter(forcetype=Heading)[0]
            if str(heading.title).strip() == self.section():
                break
        else:
            section = None # Trick pylint.
            return None
        for line in str(section).splitlines():
            matches = re.findall(r"''The result of the discussion was:''\s+"
                                 r"'''(.+?)'''", line)
            if matches:
                return matches[0]
        return None


def add_old_cfd(cfd, **kwargs):
    """Add {{Old CfD}} to the talk page."""
    talk = kwargs['old_cat'].toggleTalkPage()
    date = cfd.title(with_section=False).rpartition('/')[2]
    if talk.exists():
        wikicode = mwparserfromhell.parse(talk.text, skip_style_tags=True)
        for tpl in wikicode.ifilter_templates():
            try:
                template = pywikibot.Page(talk.site, str(tpl.name), ns=10)
                if (template not in TPL['old cfd']
                        or not tpl.has('date', ignore_empty=True)):
                    continue
                if str(tpl.get('date').value) == date:
                    # Template already present.
                    return
            except pywikibot.InvalidTitle:
                continue
    old_cfd = Template('Old CfD')
    old_cfd.add('action', kwargs['action'])
    old_cfd.add('date', date)
    old_cfd.add('section', cfd.section())
    old_cfd.add('result', kwargs['result'])
    talk.text = str(old_cfd) + '\n' + talk.text
    talk.save(summary=kwargs['summary'])


def check_action(mode, **kwargs):
    """
    Check if the action can be performeed.

    @param mode: Mode/action to check
    @type mode: str
    @kwarg old_cat: Current category
    @type old_cat: L{pywikibot.Category}
    @kwarg new_cats: Target categories
    @type new_cats: Iterable of L{pywikibot.Category}
    @rtype: bool
    """
    if mode == 'empty':
        if kwargs['new_cats']:
            pywikibot.error('empty mode has new categories for {}.'.format(
                kwargs['old_cat']))
            return False
    elif mode == 'merge':
        if not kwargs['new_cats']:
            pywikibot.error('merge mode has no new categories for {}.'.format(
                kwargs['old_cat']))
            return False
        for new_cat in kwargs['new_cats']:
            if not new_cat.exists():
                pywikibot.error('{} does not exist.'.format(new_cat))
                return False
            if new_cat.isCategoryRedirect() or new_cat.isRedirectPage():
                pywikibot.error('{} is a redirect.'.format(new_cat))
                return False
    elif mode == 'move':
        if len(kwargs['new_cats']) != 1:
            pywikibot.error('move mode has {} new categories.'
                            .format(len(kwargs['new_cats'])))
            return False
        if ((kwargs['old_cat'].isCategoryRedirect()
             or kwargs['old_cat'].isRedirectPage())
                and not kwargs['new_cats'][0].exists()):
            pywikibot.error('No target for move to {}.'.format(
                kwargs['new_cats'][0]))
            return False
        if (kwargs['new_cats'][0].isCategoryRedirect()
                or kwargs['new_cats'][0].isRedirectPage()):
            pywikibot.error('{} is a redirect.'.format(kwargs['new_cats'][0]))
            return False
    elif mode == 'retain':
        if not kwargs['old_cat'].exists():
            pywikibot.error('{} does not exist.'.format(kwargs['old_cat']))
            return False
        if kwargs['new_cats']:
            pywikibot.error('retain mode has new categories for {}.'.format(
                kwargs['old_cat']))
            return False
        if not kwargs['action'] or not kwargs['result']:
            pywikibot.error('Missing action or result for {}.'.format(
                kwargs['old_cat']))
            return False
    else:
        pywikibot.error('Unknown mode: {}.'.format(mode))
        return False
    return True


def delete_page(page, summary):
    """Delete the page and dependent pages."""
    page.delete(reason=summary, prompt=False)
    if page.exists():
        return
    page_link = page.title(as_link=True)
    for redirect in page.backlinks(filter_redirects=True):
        redirect.delete(reason=SUMMARIES['redirect'].format(page_link),
                        prompt=False)
    talk_page = page.toggleTalkPage()
    if talk_page.exists():
        talk_page.delete(reason=SUMMARIES['talk'].format(page_link),
                         prompt=False)
        talk_link = talk_page.title(as_link=True)
        for redirect in talk_page.backlinks(filter_redirects=True):
            redirect.delete(reason=SUMMARIES['redirect'].format(talk_link),
                            prompt=False)


def do_action(mode, **kwargs):
    """
    Perform the action.

    @param mode: Action to perform
    @type mode: str
    @kwarg old_cat: Current category
    @type old_cat: L{pywikibot.Category}
    @kwarg new_cats: Target categories
    @type new_cats: Iterable of L{pywikibot.Category}
    @kwarg cfd: CFD discussion
    @type cfd: L{CfdPage}
    """
    old_cat = kwargs['old_cat']
    cfd = kwargs.pop('cfd')
    cfd_link = cfd.title(as_link=True)
    gen = doc_page_add_generator(old_cat.members())
    if mode == 'empty':
        kwargs['summary'] = 'Removing {old_cat} per {cfd}'.format(
            old_cat=old_cat.title(as_link=True, textlink=True),
            cfd=cfd_link
        )
        CfdBot(gen, **kwargs).run()
        # Wait for the category to be registered as empty.
        pywikibot.sleep(pywikibot.config2.put_throttle)
        if old_cat.exists() and old_cat.isEmptyCategory():
            delete_page(old_cat, cfd_link)
    elif mode == 'merge':
        redirect = False
        if len(kwargs['new_cats']) == 1:
            new_cats = kwargs['new_cats'][0].title(as_link=True, textlink=True)
            redirect = kwargs['redirect']
        elif len(kwargs['new_cats']) == 2:
            new_cats = ' and '.join(cat.title(as_link=True, textlink=True)
                                    for cat in kwargs['new_cats'])
        else:
            new_cats = '{} categories'.format(len(kwargs['new_cats']))
        del kwargs['redirect']
        kwargs['summary'] = 'Merging {old_cat} to {new_cats} per {cfd}'.format(
            old_cat=old_cat.title(as_link=True, textlink=True),
            new_cats=new_cats, cfd=cfd_link
        )
        CfdBot(gen, **kwargs).run()
        # Wait for the category to be registered as empty.
        pywikibot.sleep(pywikibot.config2.put_throttle)
        if (old_cat.exists() and old_cat.isEmptyCategory()
                and not old_cat.isCategoryRedirect()):
            if redirect:
                redirect_cat(old_cat, kwargs['new_cats'][0],
                             'Merged to {new_cats} per {cfd}'.format(
                                 new_cats=new_cats, cfd=cfd_link))
            else:
                delete_page(old_cat, cfd_link)
    elif mode == 'move':
        noredirect = kwargs.pop('noredirect')
        if (old_cat.exists() and not old_cat.isCategoryRedirect()
                and not old_cat.isRedirectPage()
                and not kwargs['new_cats'][0].exists()):
            # Remove the last condition once merging is supported.
            old_cat.move(kwargs['new_cats'][0].title(), reason=cfd_link,
                         noredirect=noredirect)
            remove_cfd_tpl(kwargs['new_cats'][0], 'Action complete')
        kwargs['summary'] = 'Moving {old_cat} to {new_cat} per {cfd}'.format(
            old_cat=old_cat.title(as_link=True, textlink=True),
            new_cat=kwargs['new_cats'][0].title(as_link=True, textlink=True),
            cfd=cfd_link
        )
        CfdBot(gen, **kwargs).run()
    elif mode == 'retain':
        kwargs['summary'] = '{cfd} closed as {result}'.format(
            cfd=cfd_link,
            result=kwargs['result']
        )
        remove_cfd_tpl(old_cat, kwargs['summary'])
        add_old_cfd(cfd, **kwargs)


def doc_page_add_generator(generator):
    """
    Add documentation subpages for pages from another generator.

    @param generator: Pages to iterate over
    @type generator: iterable
    @rtype: generator
    """
    for page in generator:
        yield page
        if not page.namespace().subpages:
            continue
        for doc_subpage in page.site.doc_subpage:
            doc_page = pywikibot.Page(page.site, page.title() + doc_subpage)
            if doc_page.exists():
                yield doc_page


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


def parse_line(line, site, cfd_page):
    """Parse a line of wikitext from a CFD working page."""
    results = {
        'cfd_page': cfd_page,
        'prefix': '',
        'old_cat': None,
        'new_cats': list(),
        'suffix': ''
    }
    link_found = False
    wikicode = mwparserfromhell.parse(line, skip_style_tags=True)
    nodes = wikicode.filter(recursive=False)
    for index, node in enumerate(nodes, start=1):
        if isinstance(node, Text):
            if not link_found:
                results['prefix'] = str(node).strip()
            elif link_found and index == len(nodes):
                results['suffix'] = str(node).strip()
        elif isinstance(node, Wikilink):
            link_found = True
            page = pywikibot.Page(site, str(node.title))
            if page.is_categorypage():
                page = pywikibot.Category(page)
                if not results['old_cat']:
                    results['old_cat'] = page
                else:
                    results['new_cats'].append(page)
            else:
                try:
                    results['cfd_page'] = CfdPage(page)
                except ValueError:
                    raise ValueError('Found unknown link: {}'.format(page))
    return results


def parse_page(page):
    """Parse a CFD working page."""
    text = removeDisabledParts(page.text, site=page.site)
    wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
    for section in wikicode.get_sections(flat=True, include_lead=False):
        heading = section.filter(forcetype=Heading)[0]
        section_title = str(heading.title).lower()
        for mode in ['move', 'merge', 'empty', 'retain']:
            if mode in section_title:
                break
        else:
            continue
        try:
            parse_section(section, page.site, mode)
        except (ValueError, pywikibot.Error):
            pywikibot.exception(tb=True)


def parse_section(section, site, mode):
    """Parse a section of a CFD working page and invoke a bot."""
    cfd_page = None
    cfd_prefix = cfd_suffix = ''
    for line in str(section).splitlines():
        options = parse_line(line, site, cfd_page)
        if options['cfd_page'] != cfd_page:
            cfd_prefix = options['prefix']
            cfd_suffix = options['suffix']
        cfd_page = options.pop('cfd_page')
        if not cfd_page or not options['old_cat']:
            # Must have a CFD and an old cat.
            continue
        prefix = options.pop('prefix') + cfd_prefix
        suffix = options.pop('suffix') or cfd_suffix
        if 'NO BOT' in prefix:
            pywikibot.log('Bot disabled for: {}'.format(options))
            continue
        options['cfd'] = cfd_page.find_discussion(options['old_cat'])
        if mode == 'merge':
            options['redirect'] = 'REDIRECT' in prefix
        elif mode == 'move':
            options['noredirect'] = 'REDIRECT' not in prefix
        elif mode == 'retain':
            nc_matches = re.findall(r'\b(no consensus) (?:for|to) (\w+)\b',
                                    suffix, flags=re.I)
            not_matches = re.findall(r'\b(not )(\w+)\b', suffix, flags=re.I)
            if nc_matches:
                result = nc_matches[0][0]
                action = nc_matches[0][1]
            elif not_matches:
                result = not_matches[0][0] + not_matches[0][1]
                action = re.sub(r'ed$', 'e', not_matches[0][1])
            elif 'keep' in suffix.lower():
                result = 'keep'
                action = 'delete'
            else:
                action = options['cfd'].get_action(options['old_cat'])
                result = options['cfd'].get_result()
            options.update(action=action, result=result)
        if check_action(mode, **options):
            do_action(mode, **options)


def redirect_cat(cat, target, summary):
    """
    Redirect a category to another category.

    @param cat: Category to redirect
    @type cat: L{pywikibot.Category}
    @param target: Category redirect target
    @type target: L{pywikibot.Category}
    @param summary: Edit summary
    @type summary: str
    """
    tpl = Template('Category redirect')
    tpl.add('1', target.title(with_ns=False))
    cat.text = str(tpl)
    cat.save(summary=summary)


def remove_cfd_tpl(page, summary):
    """
    Remove the CfD template from the page.

    @param page: Page to edit
    @type page: L{pywikibot.Page}
    @param summary: Edit summary
    @type summary: str
    """
    text = re.sub(r'<!--\s*BEGIN CFD TEMPLATE\s*-->.*?'
                  r'<!--\s*END CFD TEMPLATE\s*-->\n*',
                  '', page.get(force=True), flags=re.I | re.M | re.S)
    wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
    for tpl in wikicode.ifilter_templates():
        try:
            template = pywikibot.Page(page.site, str(tpl.name), ns=10)
            if template in TPL['cfd']:
                wikicode.remove(tpl)
        except pywikibot.InvalidTitle:
            continue
    page.text = str(wikicode).strip()
    page.save(summary=summary)


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
    for key, value in TPL.items():
        TPL[key] = get_template_pages([pywikibot.Page(site, tpl, ns=10)
                                       for tpl in value])
    for page in gen_factory.getCombinedGenerator(preload=False):
        if page.protection().get('edit', ('', ''))[0] == 'sysop':
            parse_page(page)


if __name__ == '__main__':
    main()
