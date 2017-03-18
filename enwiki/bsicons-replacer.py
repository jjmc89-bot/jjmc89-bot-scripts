#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : BSiconsReplacer
Author : JJMC89

The following parameters are required:

-config           The page title that has the JSON config (object).
                  Options set in the config override those provided when
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

HTMLCOMMENT = re.compile(r'<!--.*?-->', flags=re.S)
ROUTEMAPBSICON = re.compile(r'(?=(\n|! !|!~|\\)(.+?)(\n|!~|~~|!@|__|!_|\\))')


def validate_config(config, site):
    """
    Validate the config and return bool.

    @param config: config to validate
    @type config: dict
    @param site: site used in the validation
    @type site: L{pywikibot.Site}

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
    Return the BSicon name.

    @param file: The file
    @type file: L{pywikibot.FilePage}

    @rtype: str
    """
    title = file.title(withNamespace=False)
    return os.path.splitext(os.path.basename(title))[0][7:]


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
            'BSiconsMap': None
        })
        self.generator = generator
        super(BSiconsReplacer, self).__init__(**kwargs)
        self.BSiconsMap = self.getOption('BSiconsMap')
        self.checkEnabledCount = 0
        # Build a list of titles for Template:Routemap.
        routemapTitles = set(['Routemap'])
        for tpl in pywikibot.Page(self.site, 'Template:Routemap').backlinks(
            filterRedirects=True,
            namespaces=self.site.namespaces.TEMPLATE
        ):
            self.templateTitles.add(tpl.title(withNamespace=False))
            self.templateTitles.add(
                tpl.title(underscore=True, withNamespace=False))
        self.routemapTitles = list(routemapTitles)
        # Build a list of BS* route diagram template titles.
        BSTemplateTitles = set()
        for template in pagegenerators.CategorizedPageGenerator(
            pywikibot.Category(self.site, 'Route diagram templates'),
            namespaces=self.site.namespaces.TEMPLATE
        ):
            if not template.title(withNamespace=False).startswith('BS'):
                continue
            BSTemplateTitles.add(template.title(withNamespace=False))
            BSTemplateTitles.add(template.title(underscore=True,
                                                withNamespace=False))
            for tpl in template.backlinks(
                filterRedirects=True,
                namespaces=self.site.namespaces.TEMPLATE
            ):
                BSTemplateTitles.add(tpl.title(withNamespace=False))
                BSTemplateTitles.add(tpl.title(underscore=True,
                                               withNamespace=False))
        self.BSTemplateTitles = list(BSTemplateTitles)

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
        text = self.current_page.get().strip()
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        replacements = set()
        # Loop over all templates on the page.
        for tpl in wikicode.filter_templates():
            if tpl.name.matches(self.routemapTitles):
                for param in tpl.params:
                    if not re.search(r'^map\d*$', str(param.name).strip()):
                        continue
                    paramValue = str(param.value)
                    matches = ROUTEMAPBSICON.findall(paramValue)
                    if not matches:
                        continue
                    for match in matches:
                        if match[1] in self.BSiconsMap:
                            replacement = self.BSiconsMap[match[1]]
                            paramValue = paramValue.replace(
                                ''.join(match),
                                match[0] + replacement + match[2]
                            )
                            replacements.add('\u2192'.join([match[1],
                                                            replacement]))
                    param.value = paramValue
            elif tpl.name.matches(self.BSTemplateTitles):
                for param in tpl.params:
                    paramValue = HTMLCOMMENT.sub('', str(param.value)).strip()
                    if paramValue in self.BSiconsMap:
                        replacement = self.BSiconsMap[paramValue]
                        param.value = re.sub(
                            r'\b%s\b' % re.escape(paramValue),
                            replacement,
                            str(param.value)
                        )
                        replacements.add('\u2192'.join([paramValue,
                                                        replacement]))
        newtext = str(wikicode).strip()
        if newtext != text:
            summary = 'Replace BSicon'
            if len(replacements) > 1:
                summary += 's'
            summary += ': ' + ', '.join(replacements)
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
                    return False
        else:
            pywikibot.error('%s does not exist.' % config.title())
            return False
    else:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False

    BSiconsMap = dict()
    pages = set()
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
        BSiconName = get_BSicon_name(localFile)
        targetBSiconName = get_BSicon_name(targetFile)
        BSiconsMap[BSiconName] = targetBSiconName
        if BSiconName.find(' ') > -1:
            BSiconsMap[BSiconName.replace(' ', '_')] = targetBSiconName
        pages = pages.union(pagegenerators.FileLinksGenerator(localFile))
    if pages:
        options['BSiconsMap'] = BSiconsMap
        gen = (page for page in pages)
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = BSiconsReplacer(gen, **options)
        bot.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
