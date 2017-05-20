#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : NFC bot
Author : JJMC89

The following parameters are supported:

-chunk            Runs the bot on intervals of the specified number of files.
                  Default 5000.

&params;
"""
import re
import sys
import mwparserfromhell
from mwparserfromhell.nodes import Tag, Wikilink
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot
from pywikibot.textlib import removeDisabledParts, replaceExcept

docuReplacements = {
    '&params;': pagegenerators.parameterHelp
}


class NFCBot(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):

    def __init__(self, generator, pageMap, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        @param pageMap: the page map used by subclasses
        @type pageMap: dict
        """
        self.generator = generator
        super().__init__(**kwargs)
        self.pageMap = pageMap
        self.exceptions = ['comment', 'nowiki', 'pre', 'source',
                           'syntaxhighlight']
        self.checkEnabledCount = 0
        self.logList = list()

    def check_enabled(self):
        """Check if the task is enabled."""
        self.checkEnabledCount += 1
        if self.checkEnabledCount % 6 != 1:
            return
        page = pywikibot.Page(
            self.site,
            'User:%s/shutoff/NFCBot' % self.site.user()
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                sys.exit('NFCBot disabled:\n%s' % content)

    def log_save_error(self, page, err):
        """
        Log to the logfile and add to self.logList.

        @param page: Page the issue was encountered on
        @type page: L{pywikibot.Page}
        @param err: Exception encountered
        @type err: Exception
        """
        if err:
            pywikibot.log(err)
            self.logList.append(str(err).replace('\n', '<br />'))

    def save_list_to_page(self, list=None, page=None):
        """
        Append the specified list to a page.

        @param list: List to save
        @type list: list
        @param page: Page to append to
        @type page: L{pywikibot.Page}
        """
        list = list or self.logList
        if not list:
            return
        page = page or pywikibot.Page(
            self.site,
            'User:%s/log/NFCBot' % self.site.user()
        )
        page.text += '\n* ' + '\n* '.join(list)
        page.text = page.text.strip()
        page.save(summary='Updating log', minor=False, botflag=False,
                  force=True)


class NFCImageRemover(NFCBot):

    def __init__(self, generator, pageMap, **kwargs):
        """Constructor."""
        super().__init__(generator, pageMap, **kwargs)
        self.fileRegex = pywikibot.textlib._get_regexes(['file'],
                                                        self.site)[0]
        namespaces = '|'.join(self.site.namespaces[6])
        self.namespaces = ''.join(['[' + c + c.swapcase() + ']' if c.isalpha()
                                   else c for c in namespaces])
        self.summary = ('[[WP:NFCC#10c]]: [[WP:NFUR|Non-free use rationale]] '
                        'missing for this page. See [[WP:NFC#Implementation]]'
                        '. Questions? [[WP:MCQ|Ask here]].')

    def treat_page(self):
        self.check_enabled()
        files = self.pageMap[self.current_page]
        text = newtext = self.current_page.get().strip()
        fileTitles = set()
        for file in files:
            fileTitle = file.title(underscore=True, withNamespace=False)
            fileTitle = re.escape(fileTitle).replace('_', '[ _]+')
            fileTitles.add(fileTitle)
            try:
                redirects = file.backlinks(filterRedirects=True)
            except pywikibot.CircularRedirect as e:
                pywikibot.error(e)
            except Exception as e:
                pywikibot.exception(e, tb=True)
            else:
                for redirect in redirects:
                    fileTitle = redirect.title(underscore=True,
                                               withNamespace=False)
                    fileTitle = re.escape(fileTitle).replace('_', '[ _]+')
                    fileTitles.add(fileTitle)
        fileTitles = '|'.join(fileTitles)
        # File link syntax
        for match in self.fileRegex.finditer(newtext):
            fileText = match.group()
            cleanFileText = removeDisabledParts(fileText)[2:-2]
            try:
                fileLink = pywikibot.Link(cleanFileText, source=self.site)
                file = pywikibot.FilePage(self.site, fileLink.title)
            except Exception as e:
                pywikibot.exception(e, tb=True)
                pywikibot.output(self.current_page)
                pywikibot.output(fileText)
                pywikibot.output(cleanFileText)
            else:
                if file in files:
                    newtext = replaceExcept(
                        newtext,
                        r'(?P<all>%s)' % re.escape(fileText),
                        r'<!-- [[WP:NFCC]] violation: \g<all> -->',
                        self.exceptions
                    )
        wikicode = mwparserfromhell.parse(newtext, skip_style_tags=True)
        # <gallery>
        fileRegex = (r'(?:\n|^)\s*(?P<all>(?::?(?:%s)[ _]*:[ _]*)?(?:%s)'
                     r'(?:.*)?)(?:\n|$)' % (self.namespaces, fileTitles))
        for tag in wikicode.ifilter(forcetype=Tag):
            if tag.tag.lower() != 'gallery':
                continue
            tag.contents = replaceExcept(
                str(tag.contents),
                re.compile(fileRegex),
                r'\n<!-- [[WP:NFCC]] violation: \g<all> -->\n',
                self.exceptions
            )
        # Template parameter values
        fileRegex = (r'(?P<all>(?:(?:%s)[ _]*:[ _]*)?(?:%s)\b)' % (
                     self.namespaces, fileTitles))
        for tpl in wikicode.ifilter_templates():
            for param in tpl.params:
                param.value = replaceExcept(
                    str(param.value),
                    re.compile(fileRegex),
                    r'<!-- [[WP:NFCC]] violation: \g<all> -->',
                    self.exceptions
                )
        newtext = str(wikicode).strip()
        if newtext != text:
            try:
                self.put_current(newtext, summary=self.summary, minor=False,
                                 callback=self.log_save_error)
            except pywikibot.OtherPageSaveError as e:
                if e.reason.find('{{bots}}'):
                    self.log_save_error(e.page, e)
        else:
            pywikibot.output('Failed to remove %s on %s.' % (
                ', '.join([file.title(asLink=True,
                                      textlink=True) for file in files]),
                self.current_page.title(asLink=True)))

    def exit(self):
        """Log issues before cleanup and exit processing."""
        self.save_list_to_page()
        super().exit()


class FURTitleReplacer(NFCBot):

    def __init__(self, generator, pageMap, **kwargs):
        """Constructor."""
        super().__init__(generator, pageMap, **kwargs)
        self.summary = 'Replace article title to match file usage'

    def treat_page(self):
        self.check_enabled()
        text = newtext = self.current_page.get().strip()
        wikicode = mwparserfromhell.parse(newtext, skip_style_tags=True)
        for redirect in self.pageMap[self.current_page]:
            title = redirect.title(underscore=True)
            titleRegex = re.compile(r'^(?P<leading>\s*)%s(?P<trailing>\s*)$'
                                    % re.escape(title).replace('_', '[ _]+'))
            targetTitle = redirect.getRedirectTarget().title()
            # Wikilinks
            for wikilink in wikicode.ifilter(forcetype=Wikilink):
                wikilink.title = titleRegex.sub(
                    targetTitle,
                    str(wikilink.title)
                )
            # |article= values
            for tpl in wikicode.ifilter_templates():
                for param in tpl.params:
                    if param.name.lower().strip() == 'article':
                        param.value = titleRegex.sub(
                            r'\g<leading>%s\g<trailing>' % targetTitle,
                            str(param.value)
                        )
        newtext = str(wikicode).strip()
        if newtext != text:
            self.put_current(newtext, summary=self.summary)
        else:
            pywikibot.output('Failed update the article title on %s.' %
                             self.current_page.title(asLink=True))


def main(*args):
    """
    Process command line arguments and invoke bot.

    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    genFactory = pagegenerators.GeneratorFactory()
    # Parse command line arguments
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        arg, sep, value = arg.partition(':')
        option = arg[1:]
        if option in ('chunk'):
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[option] = value
        else:
            options[option] = True
    files = genFactory.getCombinedGenerator()
    if not files:
        pywikibot.bot.suggest_help(missing_generator=True)
        return False
    chunk = options.pop('chunk', 5000)
    redirectsMap = dict()
    noFURMap = dict()
    fileCount = 0
    for file in files:
        if file.namespace() != site.namespaces.FILE:
            sys.exit('Incorrect namespace. Terminating.')
        if not file.exists() or file.isRedirectPage():
            continue
        fileCount += 1
        links = file.linkedPages()
        for page in file.usingPages():
            linkedToRedirect = False
            try:
                pageRedirects = page.backlinks(filterRedirects=True)
            except pywikibot.CircularRedirect as e:
                pywikibot.error(e)
                continue
            except Exception as e:
                pywikibot.exception(e, tb=True)
                continue
            for redirect in pageRedirects:
                if redirect in links:
                    linkedToRedirect = True
                    break
            if linkedToRedirect:
                if file in redirectsMap:
                    redirectsMap[file].add(redirect)
                else:
                    redirectsMap[file] = set([redirect])
            elif page not in links and file.get().find(page.title()) == -1:
                if page in noFURMap:
                    noFURMap[page].add(file)
                else:
                    noFURMap[page] = set([file])
        # Since the bot cannot start in the middle of a category (T74101),
        # run the bot in chunks.
        if fileCount % chunk == 0:
            gen = (page for page in redirectsMap.keys())
            gen = pagegenerators.PreloadingGenerator(gen)
            bot = FURTitleReplacer(gen, redirectsMap, **options)
            bot.run()
            gen = (page for page in noFURMap.keys())
            gen = pagegenerators.PreloadingGenerator(gen)
            bot = NFCImageRemover(gen, noFURMap, **options)
            bot.run()
            redirectsMap = dict()
            noFURMap = dict()
    # Final run
    gen = (page for page in redirectsMap.keys())
    gen = pagegenerators.PreloadingGenerator(gen)
    bot = FURTitleReplacer(gen, redirectsMap, **options)
    bot.run()
    gen = (page for page in noFURMap.keys())
    gen = pagegenerators.PreloadingGenerator(gen)
    bot = NFCImageRemover(gen, noFURMap, **options)
    bot.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
