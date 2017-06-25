#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script replaces BSicons.

The following parameters are required:

-config           The page title that has the JSON config (object).
                  Options set in the config override those provided when
                  running this script.
"""
# Author : JJMC89
# License: MIT
import json
import os
import re
import sys
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot

HTMLCOMMENT = re.compile(r'<!--.*?-->', flags=re.S)
ROUTEMAPBSICON = re.compile(r'(?=(\n|! !|!~|\\)(.+?)(\n|!~|~~|!@|__|!_|\\))')


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
    elif page.isRedirectPage():
        pywikibot.error('%s is a redirect.' % page.title())
        return
    text = page.get().strip()
    try:
        return json.loads(text)
    except Exception as e:
        pywikibot.exception(e, tb=True)
        return


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
        'redirects',
        'repository'
    ]
    hasKeys = []
    for key, value in config.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in requiredKeys:
            hasKeys.append(key)
        if key in 'blacklist' 'redirects' 'whitelist':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                return False
        elif key in 'BSTemplates' 'routemapTemplates':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                return False
            templates = set()
            for tpl in config[key]:
                page = pywikibot.Page(site, 'Template:%s' % tpl)
                if page.exists() and not page.isRedirectPage():
                    templates.add(page)
            config[key] = templates
        elif key == 'repository':
            if not isinstance(value, bool):
                return False
            if value and site.has_image_repository:
                fileSite = site.image_repository()
            else:
                fileSite = site
        elif key == 'replacementMap':
            pass
        elif key == 'summaryPrefix':
            if not isinstance(value, str):
                return False
        else:
            return False
    if sorted(hasKeys) != sorted(requiredKeys):
        return False
    fileSite.login()
    for key in ('blacklist', 'redirects', 'whitelist'):
        if key in config:
            generatorFactory = pagegenerators.GeneratorFactory(fileSite)
            for item in config[key]:
                if not generatorFactory.handleArg(item):
                    return False
            gen = generatorFactory.getCombinedGenerator()
            config[key] = set(gen)
        else:
            config[key] = set()
    config['redirects'] = frozenset(
        config.pop('redirects') -
        (config.pop('blacklist') - config.pop('whitelist'))
    )
    config.pop('repository', None)
    replacementMap = config.pop('replacementMap', dict())
    if isinstance(replacementMap, str):
        page = pywikibot.Page(fileSite, replacementMap)
        replacementMap = get_json_from_page(page) or dict()
    if not isinstance(replacementMap, dict):
        replacementMap = dict()
    for value in replacementMap.values():
        if not isinstance(value, str):
            return False
    config['replacementMap'] = replacementMap
    return True


def page_is_BSicon(page):
    """
    Returns whether the page is a BSicon.

    @param page: The page
    @type page: L{pywikibot.Page}

    @rtype: bool
    """
    try:
        file = pywikibot.FilePage(page)
    except:
        return False
    title = file.title(underscore=True, withNamespace=False)
    if not title.startswith('BSicon_'):
        return False
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


class BSiconsReplacer(SingleSiteBot, ExistingPageBot, NoRedirectPageBot):
    """Bot to replace BSicons."""

    def __init__(self, generator, **kwargs):
        """
        Constructor.

        @param generator: the page generator that determines on which
            pages to work
        @type generator: generator
        """
        self.availableOptions.update({
            'BSiconsMap': dict(),
            'BSTemplates': set(),
            'summaryPrefix': 'Replace BSicon(s)',
            'routemapTemplates': set()
        })
        self.generator = generator
        super(BSiconsReplacer, self).__init__(**kwargs)
        self.BSiconsMap = self.getOption('BSiconsMap')
        self.BSTemplateTitles = self.get_template_titles(
            self.getOption('BSTemplates'))
        self.bse_titles = self.get_template_titles(
            [pywikibot.Page(self.site, 'Template:BSe')])
        self.routemapTitles = self.get_template_titles(
            self.getOption('routemapTemplates'))
        self.summaryPrefix = self.getOption('summaryPrefix')

    def get_template_titles(self, templates):
        """
        Given an iterable of templates, return a set of titles.

        @param templates: iterable of templates (L{pywikibot.Page})
        @type templates: iterable

        @rtype: set
        """
        templateTitles = set()
        for template in templates:
            templateTitles.add(template.title(withNamespace=False))
            templateTitles.add(template.title(underscore=True,
                                              withNamespace=False))
            for tpl in template.backlinks(
                    filterRedirects=True,
                    namespaces=self.site.namespaces.TEMPLATE
            ):
                templateTitles.add(tpl.title(withNamespace=False))
                templateTitles.add(tpl.title(underscore=True,
                                             withNamespace=False))
        return templateTitles

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
        text = self.current_page.text
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        replacements = set()
        # Loop over all templates on the page.
        for tpl in wikicode.ifilter_templates():
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
                    if (tpl.name.matches(self.bse_titles)
                            and param.name.matches('1')):
                        current_icon = 'e' + paramValue
                    else:
                        current_icon = paramValue
                    if current_icon in self.BSiconsMap:
                        new_icon = self.BSiconsMap[current_icon]
                        if (tpl.name.matches(self.bse_titles)
                                and param.name.matches('1')):
                            if new_icon[0] != 'e':
                                # The replacement must also begin with 'e'.
                                continue
                            else:
                                replacement = new_icon[1:]
                        else:
                            replacement = new_icon
                        param.value = re.sub(
                            r'\b%s\b' % re.escape(paramValue),
                            replacement,
                            str(param.value)
                        )
                        replacements.add('\u2192'.join([current_icon,
                                                        new_icon]))
        self.put_current(
            str(wikicode),
            summary=self.summaryPrefix + ': ' + ', '.join(replacements)
        )


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
        arg, _, value = arg.partition(':')
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
    if 'config' in options:
        config = pywikibot.Page(site, options.pop('config'))
        config = get_json_from_page(config)
        if isinstance(config, dict):
            if validate_config(config, site):
                options.update(config)
            else:
                pywikibot.error('Invalid config.')
                return False
        else:
            pywikibot.error('Invalid config format.')
            return False
    else:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False

    BSiconsMap = dict()
    pages = set()
    for page in options.pop('redirects'):
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
        localFile = pywikibot.FilePage(site, page.title())
        # Both must be BSicons.
        if not (page_is_BSicon(localFile) and page_is_BSicon(targetFile)):
            continue
        BSiconName = get_BSicon_name(localFile)
        targetBSiconName = get_BSicon_name(targetFile)
        BSiconsMap[BSiconName] = targetBSiconName
        if BSiconName.find(' ') > -1:
            BSiconsMap[BSiconName.replace(' ', '_')] = targetBSiconName
        pages = pages.union(pagegenerators.FileLinksGenerator(localFile))
    for key, value in options.pop('replacementMap', dict()).items():
        try:
            localFile = pywikibot.FilePage(site, key)
            targetFile = pywikibot.FilePage(site, value)
        except Exception as e:
            pywikibot.warning(e)
            continue
        # Both must be BSicons.
        if not (page_is_BSicon(localFile) and page_is_BSicon(targetFile)):
            continue
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
    except:
        pywikibot.error("Fatal error!", exc_info=True)
    finally:
        pywikibot.stopme()
