#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : BSiconsReplacer
Author : JJMC89

The following parameters are required:

-config           The page title that has the JSON config (object).
                  Options set in the congig override those provided when
                  running this script.
"""
import json
import os
import re
import sys
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot

__version__ = '$Id$'


def validate_config(config, site):
    """
    Validate the config and return bool.

    @param config: config to validate
    @type config: dict

    @rtype: bool
    """
    pywikibot.log('Config:')
    requiredKeys = [
        'BSicons',
        'repository'
    ]
    hasKeys = []
    for key, value in config.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in requiredKeys:
            hasKeys.append(key)
        if key in ('blacklist' 'BSicons' 'whitelist'):
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                return False
        elif key == 'repository':
            if not isinstance(value, bool):
                return False
            if value and site.has_image_repository:
                fileSite = site.image_repository()
            else:
                fileSite = site
        else:
            return False
    if sorted(hasKeys) != sorted(requiredKeys):
        return False
    fileSite.login()
    for key in ('blacklist', 'BSicons', 'whitelist'):
        if key in config:
            generatorFactory = pagegenerators.GeneratorFactory(fileSite)
            for item in config[key]:
                if generatorFactory.handleArg(item):
                    continue
                else:
                    return False
            gen = generatorFactory.getCombinedGenerator()
            config[key] = set(gen)
        else:
            config[key] = set()
    config['BSicons'] = frozenset(
        config.pop('BSicons') -
        (config.pop('blacklist') - config.pop('whitelist'))
    )
    config.pop('repository', None)
    return True


def get_BSicon_name(file):
    """
    Return the file name without the extension.

    @param file: The file
    @type file: L{pywikibot.FilePage}

    @rtype: str
    """
    title = file.title(withNamespace=False)
    string = os.path.splitext(os.path.basename(title))[0][7:]
    return string


class BSiconsReplacer(
    SingleSiteBot,
    ExistingPageBot,
    NoRedirectPageBot
):

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'BSTemplateTitles': None,
            'currentFileString': None,
            'targetFileString': None
        })

        self.generator = generator
        super(BSiconsReplacer, self).__init__(site=True, **kwargs)

        self.BSTemplateTitles = self.getOption('BSTemplateTitles')
        self.currentFileString = self.getOption('currentFileString')
        self.targetFileString = self.getOption('targetFileString')
        self.routemapRegex = re.compile(
            r'(\n|! !|!~|\\)%s(\n|!~|~~|!@|__|!_|\\)'
            % re.escape(self.currentFileString))
        self.checkEnabledCount = 0

    def check_enabled(self):
        """Check if the task is enabled."""
        if self.checkEnabledCount == 7:
            self.checkEnabledCount = 1
        else:
            self.checkEnabledCount += 1
        if self.checkEnabledCount != 1:
            return

        page = pywikibot.Page(
            self.site,
            'User:%s/shutoff/%s' % (self.site.user(), self.__class__.__name__)
        )
        if page.exists():
            content = page.get().strip()
            if content != '':
                sys.exit('%s disabled:\n%s' %
                         (self.__class__.__name__, content))

    def treat_page(self):
        self.check_enabled()

        text = self.current_page.get().strip()
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)

        # Loop over all templates on the page.
        for tpl in wikicode.filter_templates():
            if tpl.name.matches('Routemap'):
                if not tpl.has('map'):
                    continue
                map = str(tpl.get('map').value).strip()
                if not self.routemapRegex.search(map):
                    continue
                map = self.routemapRegex.sub(r'\1%s\2' % self.targetFileString,
                                             map)
                tpl.add('map', map)
            elif tpl.name.matches(self.BSTemplateTitles):
                for param in tpl.params:
                    if param.value == self.currentFileString:
                        param.value = self.targetFileString

        newtext = str(wikicode).strip()
        if newtext != text:
            summary = ('Replace BSicon: %s &rarr; %s' %
                       (self.currentFileString, self.targetFileString))
            self.put_current(newtext, summary=summary)


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
        if option in (
            'config'
        ):
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[option] = value
        else:
            options[option] = True
    if 'config' in options:
        config = pywikibot.Page(site, options.pop('config'))
        if config.exists():
            config = config.get().strip()
            try:
                config = json.loads(config)
            except:
                raise
            else:
                if isinstance(config, dict):
                    if not validate_config(config, site):
                        pywikibot.error('Invalid config.')
                        return False
                    else:
                        options.update(config)
                else:
                    pywikibot.error('Invalid config format.')
        else:
            pywikibot.error('%s does not exist.' % config.title())
            return False
    else:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False

    # Build a list of BS* route diagram template titles.
    BSTemplateTitles = []
    for template in pagegenerators.CategorizedPageGenerator(
        pywikibot.Category(site, 'Route diagram templates'),
        namespaces=site.namespaces.TEMPLATE
    ):
        if not template.title(withNamespace=False).startswith('BS'):
            continue
        BSTemplateTitles.append(template.title(withNamespace=False))
        BSTemplateTitles.append(template.title(underscore=True,
                                               withNamespace=False))
        for tpl in template.backlinks(
            filterRedirects=True,
            namespaces=site.namespaces.TEMPLATE
        ):
            BSTemplateTitles.append(tpl.title(withNamespace=False))
            BSTemplateTitles.append(tpl.title(underscore=True,
                                              withNamespace=False))
    options['BSTemplateTitles'] = list(set(BSTemplateTitles))

    # Fix redirects.
    for page in options.pop('BSicons'):
        # Must be a file redirect.
        if not (page.isRedirectPage() and
                isinstance(page, pywikibot.FilePage)):
            continue
        # Target must be a file.
        try:
            targetFile = pywikibot.FilePage(page.getRedirectTarget())
        except (pywikibot.IsNotRedirectPage, ValueError) as e:
            pywikibot.warning(e)
            continue
        except Exception as e:
            pywikibot.exception(e, tb=True)
            continue
        # Target must be a BSicon.
        if not targetFile.title(underscore=True,
                                withNamespace=False).startswith('BSicon_'):
            continue
        localFile = pywikibot.FilePage(site, page.title())
        gen = pagegenerators.FileLinksGenerator(localFile)
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = BSiconsReplacer(
            gen,
            currentFileString=get_BSicon_name(localFile),
            targetFileString=get_BSicon_name(targetFile),
            **options
        )
        bot.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
