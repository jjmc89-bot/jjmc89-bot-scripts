#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script replaces BSicons.


The following parameters are supported:

-config           The page title that has the JSON config (object).
                  Any value in the object will overwrite the corresponding
                  value in the object from -global_config.

-global_config    The page title that has the JSON config (object).
                  This page must be on Wikimedia Commons. Any value in the
                  object can be overwritten by a value in the object from
                  -config.
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

HTML_COMMENT = re.compile(r'<!--.*?-->', flags=re.S)
ROUTEMAP_BSICON = re.compile(r'(?=(\n|! !|!~|\\)(.+?)(\n|!~|~~|!@|__|!_|\\))')


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict
    """
    if page.isRedirectPage():
        pywikibot.log('%s is a redirect.' % page.title())
        page = page.getRedirectTarget()
    if not page.exists():
        pywikibot.log('%s does not exist.' % page.title())
        return dict()
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error('%s does not contain valid JSON.' % page.title())
        raise
    except pywikibot.PageRelatedError:
        return dict()


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
    required_keys = ['redirects', 'repository']
    has_keys = list()
    for key, value in config.items():
        pywikibot.log('-%s = %s' % (key, value))
        if key in required_keys:
            has_keys.append(key)
        if key in 'blacklist' 'redirects' 'whitelist':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                return False
        elif key in 'BS_templates' 'routemap_templates':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                return False
            templates = set()
            for tpl in config[key]:
                page = pywikibot.Page(site, 'Template:%s' % tpl)
                if page.exists():
                    templates.add(page)
            config[key] = templates
        elif key == 'repository':
            if not isinstance(value, bool):
                return False
            if value and site.has_image_repository:
                file_site = site.image_repository()
            else:
                file_site = site
        elif key == 'replacement_map':
            pass
        elif key == 'summary_prefix':
            if not isinstance(value, str):
                return False
        else:
            return False
    if sorted(has_keys) != sorted(required_keys):
        return False
    file_site.login()
    for key in ('blacklist', 'redirects', 'whitelist'):
        if key in config:
            generator_factory = pagegenerators.GeneratorFactory(file_site)
            for item in config[key]:
                if not generator_factory.handleArg(item):
                    return False
            gen = generator_factory.getCombinedGenerator()
            config[key] = set(gen)
        else:
            config[key] = set()
    config['redirects'] = frozenset(
        config.pop('redirects') - (config.pop('blacklist')
                                   - config.pop('whitelist'))
    )
    config.pop('repository', None)
    replacement_map = config.pop('replacement_map', dict())
    if isinstance(replacement_map, str):
        page = pywikibot.Page(file_site, replacement_map)
        replacement_map = get_json_from_page(page) or dict()
    if not isinstance(replacement_map, dict):
        replacement_map = dict()
    for value in replacement_map.values():
        if not isinstance(value, str):
            return False
    config['replacement_map'] = replacement_map
    return True


def page_is_bsicon(page):
    """
    Returns whether the page is a BSicon.

    @param page: The page
    @type page: L{pywikibot.Page}

    @rtype: bool
    """
    if page.namespace() != page.site.namespaces.FILE:
        return False
    if not page.title(underscore=True,
                      withNamespace=False).startswith('BSicon_'):
        return False
    return True


def get_bsicon_name(file):
    """
    Return the BSicon name.

    @param file: The file
    @type file: L{pywikibot.FilePage}

    @rtype: str
    """
    return os.path.splitext(os.path.basename(file.title(
        withNamespace=False)))[0][7:]


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
            'bsicons_map': dict(),
            'BS_templates': set(),
            'summary_prefix': 'Replace BSicon(s)',
            'routemap_templates': set()
        })
        self.generator = generator
        super().__init__(**kwargs)
        self.bs_titles = self.get_template_titles(
            self.getOption('BS_templates'))
        self.routemap_titles = self.get_template_titles(
            self.getOption('routemap_templates'))
        self.prefix_map = {
            'e': self.get_template_titles([
                pywikibot.Page(self.site, 'Template:BSe'),
                pywikibot.Page(self.site, 'Template:BS1e'),
                pywikibot.Page(self.site, 'Template:JBSu'),
                pywikibot.Page(self.site, 'Template:JBS1u'),
                pywikibot.Page(self.site, 'Template:ZCn'),
                pywikibot.Page(self.site, 'Template:ZC1n'),
                pywikibot.Page(self.site, 'Template:ŽČn'),
                pywikibot.Page(self.site, 'Template:ŽČ1n'),
                pywikibot.Page(self.site, 'Template:FLe'),
                pywikibot.Page(self.site, 'Template:FL1e')
            ]),
            'u': self.get_template_titles([
                pywikibot.Page(self.site, 'Template:BSu'),
                pywikibot.Page(self.site, 'Template:BS1u'),
                pywikibot.Page(self.site, 'Template:ZCm'),
                pywikibot.Page(self.site, 'Template:ZC1m'),
                pywikibot.Page(self.site, 'Template:ŽČm'),
                pywikibot.Page(self.site, 'Template:ŽČ1m'),
                pywikibot.Page(self.site, 'Template:FLm'),
                pywikibot.Page(self.site, 'Template:FL1m')
            ]),
            'ue': self.get_template_titles([
                pywikibot.Page(self.site, 'Template:BSue'),
                pywikibot.Page(self.site, 'Template:BS1ue'),
                pywikibot.Page(self.site, 'Template:FLme'),
                pywikibot.Page(self.site, 'Template:FL1me')
            ]),
        }

    def get_template_titles(self, templates):
        """
        Given an iterable of templates, return a set of titles.

        @param templates: iterable of templates (L{pywikibot.Page})
        @type templates: iterable

        @rtype: set
        """
        titles = set()
        for template in templates:
            if template.isRedirectPage():
                template = template.getRedirectTarget()
            if not template.exists():
                continue
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
        wikicode = mwparserfromhell.parse(self.current_page.text,
                                          skip_style_tags=True)
        replacements = set()
        # Loop over all templates on the page.
        for tpl in wikicode.ifilter_templates():
            if tpl.name.matches(self.routemap_titles):
                for param in tpl.params:
                    if not re.search(r'^map\d*$', str(param.name).strip()):
                        continue
                    param_value = str(param.value)
                    matches = ROUTEMAP_BSICON.findall(param_value)
                    if not matches:
                        continue
                    for match in matches:
                        if match[1] in self.getOption('bsicons_map'):
                            replacement = self.getOption('bsicons_map')[
                                match[1]]
                            param_value = param_value.replace(
                                ''.join(match),
                                match[0] + replacement + match[2]
                            )
                            replacements.add('\u2192'.join([match[1],
                                                            replacement]))
                    param.value = param_value
            elif tpl.name.matches(self.bs_titles):
                for param in tpl.params:
                    param_value = HTML_COMMENT.sub('',
                                                   str(param.value)).strip()
                    prefix = ''
                    if param.name.matches('1'):
                        for key, value in self.prefix_map.items():
                            if tpl.name.matches(value):
                                prefix = key
                                break
                    current_icon = prefix + param_value
                    if current_icon in self.getOption('bsicons_map'):
                        new_icon = self.getOption('bsicons_map')[current_icon]
                        # The replacement must have the same prefix.
                        if new_icon[:len(prefix)] == prefix:
                            param.value = re.sub(
                                r'\b%s\b' % re.escape(param_value),
                                new_icon[len(prefix):],
                                str(param.value)
                            )
                            replacements.add('\u2192'.join([current_icon,
                                                            new_icon]))
        self.put_current(
            str(wikicode),
            summary='{}: {}'.format(self.getOption('summary_prefix'),
                                    ', '.join(replacements))
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
    gen_factory = pagegenerators.GeneratorFactory()
    for arg in local_args:
        if gen_factory.handleArg(arg):
            continue
        arg, _, value = arg.partition(':')
        arg = arg[1:]
        if arg in 'config' 'global_config':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for %s' % arg,
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if 'config' not in options and 'global_config' not in options:
        pywikibot.bot.suggest_help(
            additional_text='Missing parameter(s) "config" or "global_config"'
        )
        return False
    if 'global_config' in options:
        config = get_json_from_page(pywikibot.Page(
            pywikibot.Site('commons', 'commons'),
            options.pop('global_config')
        ))
    else:
        config = dict()
    if 'config' in options:
        config.update(get_json_from_page(
            pywikibot.Page(site, options.pop('config'))))
    if validate_config(config, site):
        options.update(config)
    else:
        pywikibot.error('Invalid config.')
        return False

    bsicons_map = dict()
    pages = set()
    for page in options.pop('redirects'):
        # Must be a file redirect.
        if not (page.isRedirectPage() and
                isinstance(page, pywikibot.FilePage)):
            continue
        # Target must be a file.
        try:
            target_file = pywikibot.FilePage(page.getRedirectTarget())
        except (pywikibot.IsNotRedirectPage, ValueError) as e:
            pywikibot.warning(e)
            continue
        local_file = pywikibot.FilePage(site, page.title())
        # Both must be BSicons.
        if not (page_is_bsicon(local_file) and page_is_bsicon(target_file)):
            continue
        bsicon_name = get_bsicon_name(local_file)
        target_bsicon_name = get_bsicon_name(target_file)
        bsicons_map[bsicon_name] = target_bsicon_name
        if bsicon_name.find(' ') > -1:
            bsicons_map[bsicon_name.replace(' ', '_')] = target_bsicon_name
        pages = pages.union(pagegenerators.FileLinksGenerator(local_file))
    for key, value in options.pop('replacement_map', dict()).items():
        try:
            local_file = pywikibot.FilePage(site, key)
            target_file = pywikibot.FilePage(site, value)
        except ValueError as e:
            pywikibot.warning(e)
            continue
        # Both must be BSicons.
        if not (page_is_bsicon(local_file) and page_is_bsicon(target_file)):
            continue
        bsicon_name = get_bsicon_name(local_file)
        target_bsicon_name = get_bsicon_name(target_file)
        bsicons_map[bsicon_name] = target_bsicon_name
        if bsicon_name.find(' ') > -1:
            bsicons_map[bsicon_name.replace(' ', '_')] = target_bsicon_name
        pages = pages.union(pagegenerators.FileLinksGenerator(local_file))
    if pages:
        options['bsicons_map'] = bsicons_map
        gen = (page for page in pages)
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = BSiconsReplacer(gen, **options)
        bot.run()


if __name__ == "__main__":
    main()
