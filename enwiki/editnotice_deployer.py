#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script deploys editnotices.

The following parameters are supported:

-editnoticeTemplate Title of the editnotice template

-subject_Only     Restrict to subject pages

-talk_only        Restrict to talk pages

-to_subject       Add each talk page's subject page

-to_talk          Add each subject page's talk page

&params;
"""
# Author : JJMC89
# License: MIT
import sys
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, CurrentPageBot

docuReplacements = { # pylint: disable=invalid-name
    '&params;': pagegenerators.parameterHelp
}


def validate_options(options, site):
    """
    Validate the options and return bool.

    @param options: options to validate
    @type options: dict

    @rtype: bool
    """
    pywikibot.log('Options:')
    required_keys = ['editnotice_template']
    has_keys = list()
    for key, value in options.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in required_keys:
            has_keys.append(key)
        if key in ('subject_only', 'talk_only', 'to_subject', 'to_talk'):
            pass
        elif key == 'editnotice_template':
            if isinstance(key, str):
                editnotice_page = pywikibot.Page(site, 'Template:%s' % value)
                if not editnotice_page.exists():
                    return False
            else:
                return False
    if sorted(has_keys) != sorted(required_keys):
        return False
    options['editnotice_page'] = editnotice_page
    options.pop('editnotice_template')
    return True


def page_with_subject_page_generator( # pylint: disable=invalid-name
        generator, return_subject_only=False):
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


def subject_page_generator(generator):
    """Yield subject pages from another generator."""
    for page in generator:
        if not page.isTalkPage():
            yield page


def talk_page_generator(generator):
    """Yield talk pages from another generator."""
    for page in generator:
        if page.isTalkPage():
            yield page


def editnotice_page_generator(generator):
    """Yield editnotice pages for existing, non-redirect pages from another
    generator."""
    for page in generator:
        if page.exists() and not page.isRedirectPage():
            title = page.title(withSection=False)
            editnotice_title = 'Template:Editnotices/Page/%s' % title
            editnotice_page = pywikibot.Page(page.site, editnotice_title)
            yield editnotice_page


class EditnoticeDeployer(SingleSiteBot, CurrentPageBot):
    """Bot to deploy editnotices."""

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'editnotice_page': None
        })
        self.generator = generator
        super().__init__(**kwargs)
        self.editnotice_page_titles = self.get_template_titles(
            [self.getOption('editnotice_page')])

    def get_template_titles(self, templates):
        """
        Given an iterable of templates, return a set of titles.

        @param templates: iterable of templates (L{pywikibot.Page})
        @type templates: iterable

        @rtype: set
        """
        titles = set()
        for template in templates:
            titles.add(template.title(withNamespace=False))
            titles.add(template.title(underscore=True, withNamespace=False))
            for tpl in template.backlinks(
                    filterRedirects=True,
                    namespaces=self.site.namespaces.TEMPLATE
            ):
                titles.add(tpl.title(withNamespace=False))
                titles.add(tpl.title(underscore=True, withNamespace=False))
        return titles

    def check_enabled(self):
        """Check if the task is enabled."""
        if self._treat_counter % 6 != 0:
            return
        page = pywikibot.Page(
            self.site,
            'User:%s/shutoff/%s' % (self.site.user(), self.__class__.__name__)
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                sys.exit('%s disabled:\n%s' %
                         (self.__class__.__name__, content))

    def treat_page(self):
        """Process one page."""
        self.check_enabled()
        skip = False
        if (not self.current_page.exists() or
                self.current_page.isRedirectPage()):
            text = ''
        else:
            text = self.current_page.text
            wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
            # Check to make sure the editnotice isn't already there.
            for tpl in wikicode.filter_templates():
                if tpl.name.matches(self.editnotice_page_titles):
                    skip = True
                    break
        text = ('%s\n{{%s}}' % (text,
                                self.getOption('editnotice_page').title(
                                    withNamespace=False))).strip()
        if not skip:
            self.put_current(
                text,
                summary=('Deploying editnotice: {{%s}}' % self.getOption(
                    'editnotice_page').title(withNamespace=False)),
                minor=False
            )


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'subject_only': False,
        'talk_only': False,
        'to_subject': False,
        'to_talk': False
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    gen_factory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg == 'editnotice_template':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if not validate_options(options, site):
        pywikibot.error('Invalid options.')
        return False
    gen = gen_factory.getCombinedGenerator()

    if gen:
        if options['to_subject']:
            gen = page_with_subject_page_generator(
                gen,
                return_subject_only=options['subject_only']
            )
        elif options['to_talk']:
            gen = pagegenerators.PageWithTalkPageGenerator(
                gen,
                return_talk_only=options['talk_only']
            )
        elif options['subject_only']:
            gen = subject_page_generator(gen)
        elif options['talk_only']:
            gen = talk_page_generator(gen)
        gen = editnotice_page_generator(gen)
        for key in ('subject_only', 'talk_only', 'to_subject', 'to_talk'):
            options.pop(key, None)
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = EditnoticeDeployer(gen, **options)
        bot.run()
        return True
    pywikibot.bot.suggest_help(missing_generator=True)
    return False


if __name__ == "__main__":
    main()
