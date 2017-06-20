#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : MagicLinksReplacer
Author : JJMC89

The following parameters are required:

-config           The page title that has the JSON config (object).

The following parameters are supported:

&params;
"""
import json
import re
import sys
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot
from pywikibot.textlib import replaceExcept

docuReplacements = {
    '&params;': pagegenerators.parameterHelp
}


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict or None
    """
    if not page.exists():
        pywikibot.error('%s does not exist.' % page.title())
        return
    text = page.get().strip()
    try:
        return json.loads(text)
    except:
        return


def validate_config(config):
    """
    Validate the config and return bool.

    @param config: config to validate
    @type config: dict

    @rtype: bool
    """
    pywikibot.log('Config:')
    for key, value in config.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in ('ISBN' 'PMID' 'RFC' 'summary'):
            if not isinstance(value, str):
                return False
            config[key] = value.strip() or None
        else:
            return False
    return True


class MagicLinksReplacer(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'summary': None,
            'ISBN': None,
            'PMID': None,
            'RFC': None
        })
        self.generator = generator
        super().__init__(**kwargs)
        self.summary = self.getOption('summary')
        space = r'(?:[^\S\n]|&nbsp;|&\#0*160;|&\#[Xx]0*[Aa]0;)'
        spaces = r'{space}+'.format(space=space)
        space_dash = r'(?:-|{space})'.format(space=space)
        self.ISBN_regex = re.compile(
            r'\bISBN(?P<separator>{spaces})(?P<value>(?:97[89]{space_dash}?)?'
            r'(?:[0-9]{space_dash}?){{9}}[0-9Xx])\b'.format(
                spaces=spaces, space_dash=space_dash)
        )
        self.ISBN_replacement = self.getOption('ISBN')
        self.PMID_regex = re.compile(
            r'\bPMID(?P<separator>{spaces})(?P<value>[0-9]+)\b'.format(
                spaces=spaces)
        )
        self.PMID_replacement = self.getOption('PMID')
        self.RFC_regex = re.compile(
            r'\bRFC(?P<separator>{spaces})(?P<value>[0-9]+)\b'.format(
                spaces=spaces)
        )
        self.RFC_replacement = self.getOption('RFC')
        self.exceptions = ['comment', 'header', 'link', 'interwiki'
                           'property', 'invoke', 'category', 'file']
        self.tags = ['gallery', 'math', 'nowiki', 'pre', 'source', 'score',
                     'syntaxhighlight']
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
            content = page.get(force=True).strip()
            if content:
                sys.exit('%s disabled:\n%s' %
                         (self.__class__.__name__, content))

    def mask_text(self, text, mask, regex):
        try:
            key = max(mask.keys()) + 1
        except ValueError:
            key = 1
        matches = [match[0] if isinstance(match, tuple) else match
                   for match in regex.findall(text)]
        matches = sorted(matches, key=len, reverse=True)
        for match in matches:
            mask[key] = match
            text = text.replace(match, '!@#bot!@#masked!@#%s!@#' % key)
            key += 1
        return text

    def unmask_text(self, text, mask):
        while text.find('!@#bot!@#masked!@#') > -1:
            for key, value in mask.items():
                text = text.replace('!@#bot!@#masked!@#%s!@#' % key, value)
        return text

    def mask_URLs(self, text, mask):
        # Based on pywikibot.textlib.compileLinkR
        # and https://gist.github.com/gruber/249502
        URL = (
            r'''(?:[a-z][\w-]+://[^\]\s<>"]*'''
            r'''[^\]\s\.:;,<>"\|\)`!{}'?«»“”‘’])'''
        )
        bracket_URL_regex = re.compile(r'(\[%s[^\]]*\])' % URL, flags=re.I)
        text = self.mask_text(text, mask, bracket_URL_regex)
        bare_URL_regex = re.compile(r'\b(%s)' % URL, flags=re.I)
        text = self.mask_text(text, mask, bare_URL_regex)
        return text

    def mask_HTML_tags_content(self, text, mask):
        tags_content_regex = re.compile(
            r'(<(?P<tag>%s)\b.*?</(?P=tag)>)' % r'|'.join(self.tags),
            flags=re.I
        )
        text = self.mask_text(text, mask, tags_content_regex)
        return text

    def mask_HTML_tags(self, text, mask):
        tags_regex = re.compile(
            r'''(<\/?\w+(?:\s+\w+(?:\s*=\s*(?:(?:"[^"]*")|(?:'[^']*')|'''
            r'''[^>\s]+))?)*\s*\/?>)''',
            flags=re.S
        )
        text = self.mask_text(text, mask, tags_regex)
        return text

    def treat_page(self):
        self.check_enabled()
        text = newtext = self.current_page.get().strip()
        mask = dict()
        newtext = self.mask_HTML_tags_content(newtext, mask)
        newtext = self.mask_HTML_tags(newtext, mask)
        newtext = self.mask_URLs(newtext, mask)
        if self.ISBN_replacement:
            newtext = replaceExcept(newtext, self.ISBN_regex,
                                    self.ISBN_replacement, self.exceptions)
        if self.PMID_replacement:
            newtext = replaceExcept(newtext, self.PMID_regex,
                                    self.PMID_replacement, self.exceptions)
        if self.RFC_replacement:
            newtext = replaceExcept(newtext, self.RFC_regex,
                                    self.RFC_replacement, self.exceptions)
        newtext = self.unmask_text(newtext, mask)
        if newtext != text:
            self.put_current(newtext, summary=self.summary)


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
    # Parse command line arguments
    genFactory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        arg, sep, value = arg.partition(':')
        option = arg[1:]
        if option == 'config':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[option] = value
        else:
            options[option] = True
    gen = genFactory.getCombinedGenerator()
    if 'config' not in options:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    config = pywikibot.Page(site, options.pop('config'))
    config = get_json_from_page(config)
    if isinstance(config, dict):
        if validate_config(config):
            options.update(config)
        else:
            pywikibot.error('Invalid config.')
            return False
    else:
        pywikibot.error('Invalid config format.')
        return False
    if gen:
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = MagicLinksReplacer(gen, **options)
        bot.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
