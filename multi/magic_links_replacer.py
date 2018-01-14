#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script replaces magic links.

The following parameters are required:

-config           The page title that has the JSON config (object).

The following parameters are supported:

&params;
"""
# Author : JJMC89
# License: MIT
import json
import re
import sys
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot
from pywikibot.textlib import replaceExcept

docuReplacements = { #pylint: disable=invalid-name
    '&params;': pagegenerators.parameterHelp
}

# For _create_regexes().
_REGEXES = dict()


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict or None
    """
    if not page.exists():
        pywikibot.error('%s does not exist.' % page.title())
        return None
    elif page.isRedirectPage():
        pywikibot.error('%s is a redirect.' % page.title())
        return None
    elif page.isEmpty():
        pywikibot.log('%s is empty.' % page.title())
        return None
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error('%s does not contain valid JSON.' % page.title())
        raise


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
        if key in 'ISBN' 'PMID' 'RFC' 'summary':
            if not isinstance(value, str):
                return False
            config[key] = value.strip() or None
        else:
            return False
    return True


def _create_regexes():
    """Fill (and possibly overwrite) _REGEXES with default regexes."""
    space = r'(?:[^\S\n]|&nbsp;|&\#0*160;|&\#[Xx]0*[Aa]0;)'
    spaces = r'{space}+'.format(space=space)
    space_dash = r'(?:-|{space})'.format(space=space)
    tags = ['gallery', 'math', 'nowiki', 'pre', 'score', 'source',
            'syntaxhighlight']
    # Based on pywikibot.textlib.compileLinkR
    # and https://gist.github.com/gruber/249502
    url = r'''(?:[a-z][\w-]+://[^\]\s<>"]*[^\]\s\.:;,<>"\|\)`!{}'?«»“”‘’])'''
    _REGEXES.update({
        'bare_url': re.compile(r'\b({})'.format(url), flags=re.I),
        'bracket_url': re.compile(r'(\[{}[^\]]*\])'.format(url), flags=re.I),
        'ISBN': re.compile(
            r'\bISBN(?P<separator>{spaces})(?P<value>(?:97[89]{space_dash}?)?'
            r'(?:[0-9]{space_dash}?){{9}}[0-9Xx])\b'.format(
                spaces=spaces, space_dash=space_dash)
        ),
        'PMID': re.compile(
            r'\bPMID(?P<separator>{spaces})(?P<value>[0-9]+)\b'.format(
                spaces=spaces)
        ),
        'RFC': re.compile(
            r'\bRFC(?P<separator>{spaces})(?P<value>[0-9]+)\b'.format(
                spaces=spaces)
        ),
        'tags': re.compile(
            r'''(<\/?\w+(?:\s+\w+(?:\s*=\s*(?:(?:"[^"]*")|(?:'[^']*')|'''
            r'''[^>\s]+))?)*\s*\/?>)'''
        ),
        'tags_content': re.compile(r'(<(?P<tag>%s)\b.*?</(?P=tag)>)'
                                   % r'|'.join(tags), flags=re.I | re.M)
    })


def split_into_sections(text):
    """
    Splits wikitext into sections based on any level wiki heading.

    @param text: Text to split
    @type text: str

    @rtype: list
    """
    headings_regex = re.compile(r'^={1,6}.*?={1,6}(?: *<!--.*?-->)?\s*$',
                                flags=re.M)
    sections = list()
    last_match_start = 0
    for match in headings_regex.finditer(text):
        match_start = match.start()
        if match_start > 0:
            sections.append(text[last_match_start:match_start])
            last_match_start = match_start
    sections.append(text[last_match_start:])
    return sections


class MagicLinksReplacer(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    """Bot to replace magic links."""

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
        _create_regexes()
        self.replace_exceptions = [_REGEXES[key] for key in
                                   ('bare_url', 'bracket_url', 'tags_content',
                                    'tags')]
        self.replace_exceptions += ['category', 'comment', 'file',
                                    'interwiki', 'invoke', 'link', 'property',
                                    'template']

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
        text = ''
        sections = split_into_sections(self.current_page.text)
        for section in sections:
            if self.getOption('ISBN'):
                section = replaceExcept(section, _REGEXES['ISBN'],
                                        self.getOption('ISBN'),
                                        self.replace_exceptions)
            if self.getOption('PMID'):
                section = replaceExcept(section, _REGEXES['PMID'],
                                        self.getOption('PMID'),
                                        self.replace_exceptions)
            if self.getOption('RFC'):
                section = replaceExcept(section, _REGEXES['RFC'],
                                        self.getOption('RFC'),
                                        self.replace_exceptions)
            text += section
        self.put_current(text, summary=self.getOption('summary'))


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
    gen_factory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg == 'config':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    gen = gen_factory.getCombinedGenerator()
    if 'config' not in options:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    config = pywikibot.Page(site, options.pop('config'))
    config = get_json_from_page(config)
    if validate_config(config):
        options.update(config)
    else:
        pywikibot.error('Invalid config.')
        return False
    if gen:
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = MagicLinksReplacer(gen, **options)
        bot.run()
    return True


if __name__ == "__main__":
    main()
