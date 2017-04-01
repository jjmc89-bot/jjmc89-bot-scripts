#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : EditnoticeDeployer
Author : JJMC89

The following parameters are supported:

-editnoticeTemplate Title of the editnotice template

-subjectOnly      Restrict to subject pages

-talkOnly         Restrict to talk pages

-toSubject        Add each talk page's subject page

-toTalk           Add each subject page's talk page

&params;
"""
import sys
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, CurrentPageBot

__version__ = '$Id$'

docuReplacements = {
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
    requiredKeys = [
        'editnoticeTemplate'
    ]
    hasKeys = []
    for key, value in options.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in requiredKeys:
            hasKeys.append(key)
        if key in ('subjectOnly', 'talkOnly', 'toSubject', 'toTalk'):
            pass
        elif key == 'editnoticeTemplate':
            if isinstance(key, str):
                editnoticePage = pywikibot.Page(site, 'Template:%s' % value)
                if not editnoticePage.exists():
                    return False
            else:
                return False
    if sorted(hasKeys) != sorted(requiredKeys):
        return False
    options['editnoticePage'] = editnoticePage
    options.pop('editnoticeTemplate')
    return True


def PageWithSubjectPageGenerator(generator, return_subject_only=False):
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


def SubjectPageGenerator(generator):
    """Yield subject pages from another generator."""
    for page in generator:
        if not page.isTalkPage():
            yield page


def TalkPageGenerator(generator):
    """Yield talk pages from another generator."""
    for page in generator:
        if page.isTalkPage():
            yield page


def EditnoticePageGenerator(generator):
    """Yield editnotice pages for existing, non-redirect pages from another
    generator."""
    for page in generator:
        if page.exists() and not page.isRedirectPage():
            title = page.title(withSection=False)
            editnoticeTitle = 'Template:Editnotices/Page/%s' % title
            editnoticePage = pywikibot.Page(page.site, editnoticeTitle)
            yield editnoticePage


class EditnoticeDeployer(SingleSiteBot, CurrentPageBot):

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'editnoticePage': None
        })

        self.generator = generator
        super(EditnoticeDeployer, self).__init__(**kwargs)

        self.editnoticePage = self.getOption('editnoticePage')
        self.editnoticePageTitles = [
            self.editnoticePage.title(withNamespace=False),
            self.editnoticePage.title(underscore=True, withNamespace=False)
        ]
        for tpl in self.editnoticePage.backlinks(
            filterRedirects=True,
            namespaces=self.site.namespaces.TEMPLATE
        ):
            self.editnoticePageTitles.append(tpl.title(withNamespace=False))
            self.editnoticePageTitles.append(tpl.title(underscore=True,
                                                       withNamespace=False))
        self.summary = ('Deploying editnotice: {{%s}}' %
                        self.editnoticePage.title(withNamespace=False))

        self.checkEnabledCount = 0

    def check_enabled(self):
        """Check if the task is enabled."""
        self.checkEnabledCount += 1
        if self.checkEnabledCount % 6 != 1:
            return
        page = pywikibot.Page(
            self.site,
            'User:%s/shutoff/%s' % (self.site.user(), self.__class__.__name__)
        )
        if page.exists():
            content = page.get().strip()
            if content:
                sys.exit('%s disabled:\n%s' %
                         (self.__class__.__name__, content))

    def treat_page(self):
        self.check_enabled()
        skipPage = False
        if (not self.current_page.exists() or
                self.current_page.isRedirectPage()):
            text = ''
        else:
            text = self.current_page.get().strip()
            wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
            # Check to make sure the editnotice isn't already there.
            for tpl in wikicode.filter_templates():
                if tpl.name.matches(self.editnoticePageTitles):
                    skipPage = True
                    break
        newtext = ('%s\n{{%s}}' % (text,
                                   self.editnoticePage.title(
                                       withNamespace=False))).strip()
        if not skipPage and newtext != text:
            self.put_current(newtext, summary=self.summary, minor=False)


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {
        'subjectOnly': False,
        'talkOnly': False,
        'toSubject': False,
        'toTalk': False
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    genFactory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        arg, sep, value = arg.partition(':')
        option = arg[1:]
        if option in (
            'editnoticeTemplate'
        ):
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[option] = value
        else:
            options[option] = True
    if not validate_options(options, site):
        pywikibot.error('Invalid options.')
        return False
    gen = genFactory.getCombinedGenerator()

    if gen:
        if options['toSubject']:
            gen = PageWithSubjectPageGenerator(
                gen,
                return_subject_only=options['subjectOnly']
            )
        elif options['toTalk']:
            gen = pagegenerators.PageWithTalkPageGenerator(
                gen,
                return_talk_only=options['talkOnly']
            )
        elif options['subjectOnly']:
            gen = SubjectPageGenerator(gen)
        elif options['talkOnly']:
            gen = TalkPageGenerator(gen)
        gen = EditnoticePageGenerator(gen)
        for key in ('subjectOnly', 'talkOnly', 'toSubject', 'toTalk'):
            options.pop(key, None)
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = EditnoticeDeployer(gen, **options)
        bot.run()
        return True
    else:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
