#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This script replaces BSicons.


The following arguments are required:

-config           The page title that has the JSON config (object).
                  This page must be on Wikimedia Commons. Any value in the
                  object can be overwritten by a value in the object from
                  -local_config.

The following arguments are supported:

-local_config     The page title that has the JSON config (object).
                  Any value in the object will overwrite the corresponding
                  value in the object from -config.
                  If not provided, it will be the same as -config.
"""
# Author : JJMC89
# License: MIT
import copy
import json
import os
import re
from html import unescape as html_unescape
from urllib.parse import unquote as url_unquote
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import (MultipleSitesBot, FollowRedirectPageBot,
                           ExistingPageBot)

HTML_COMMENT = re.compile(r'<!--.*?-->', flags=re.S)
ROUTEMAP_BSICON = re.compile(
    r'(?=((?:\n|! !|!~|\\)[ \t]*)([^\\~\n]+?)([ \t]*(?:\n|!~|~~|!@|__|!_|\\)))'
)


def get_json_from_page(page):
    """
    Return JSON from the page.

    @param page: Page to read
    @type page: L{pywikibot.Page}

    @rtype: dict
    """
    if page.isRedirectPage():
        pywikibot.log('{} is a redirect.'.format(page.title()))
        page = page.getRedirectTarget()
    if not page.exists():
        pywikibot.log('{} does not exist.'.format(page.title()))
        return dict()
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error('{} does not contain valid JSON.'.format(page.title()))
        raise
    except pywikibot.PageRelatedError:
        return dict()


def get_template_titles(templates):
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
                namespaces=template.site.namespaces.TEMPLATE
        ):
            titles.add(tpl.title(withNamespace=False))
            titles.add(tpl.title(underscore=True, withNamespace=False))
    return titles


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
    required_keys = ['redirects']
    has_keys = list()
    for key, value in config.items():
        pywikibot.log('-{} = {}'.format(key, value))
        if key in required_keys:
            has_keys.append(key)
        if key in 'blacklist' 'redirects' 'whitelist':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                pywikibot.log('Invalid type.')
                return False
    if sorted(has_keys) != sorted(required_keys):
        pywikibot.log('Missing one more required keys.')
        return False
    for key in ('blacklist', 'redirects', 'whitelist'):
        if key in config:
            generator_factory = pagegenerators.GeneratorFactory(site)
            for item in config[key]:
                if not generator_factory.handleArg(item):
                    pywikibot.log('Invalid generator.')
                    return False
            gen = generator_factory.getCombinedGenerator()
            config[key] = set(gen)
        else:
            config[key] = set()
    config['redirects'] = frozenset(
        config.pop('redirects') - (config.pop('blacklist')
                                   - config.pop('whitelist'))
    )
    replacement_map = config.pop('replacement_map', dict())
    if isinstance(replacement_map, str):
        page = pywikibot.Page(site, replacement_map)
        replacement_map = get_json_from_page(page)
    elif not isinstance(replacement_map, dict):
        replacement_map = dict()
    for value in replacement_map.values():
        if not isinstance(value, str):
            pywikibot.log('Invalid type.')
            return False
    config['replacement_map'] = replacement_map
    return True


def validate_local_config(config, site):
    """
    Validate the local config and return bool.

    @param config: config to validate
    @type config: dict
    @param site: site used in the validation
    @type site: L{pywikibot.Site}

    @rtype: bool
    """
    pywikibot.log('Config for {}:'.format(site))
    required_keys = ['summary_prefix']
    has_keys = list()
    for key, value in config.items():
        pywikibot.log('-{} = {}'.format(key, value))
        if key in required_keys:
            has_keys.append(key)
        if key == 'BS_templates':
            if isinstance(value, str):
                config[key] = {'': [value]}
            elif isinstance(value, list):
                config[key] = {'': value}
            elif not isinstance(value, dict):
                pywikibot.log('Invalid type.')
                return False
            tpl_map = dict()
            for prefix, templates in config[key].items():
                if isinstance(templates, str):
                    templates = [templates]
                elif not isinstance(templates, list):
                    pywikibot.log('Invalid type.')
                    return False
                tpl_map[prefix] = get_template_titles([pywikibot.Page(
                    site, 'Template:{}'.format(tpl)) for tpl in templates])
            config[key] = tpl_map
        elif key in 'railway_track_templates' 'routemap_templates':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                pywikibot.log('Invalid type.')
                return False
            config[key] = get_template_titles([pywikibot.Page(
                site, 'Template:{}'.format(tpl)) for tpl in config[key]])
        elif key == 'summary_prefix':
            if not isinstance(value, str):
                pywikibot.log('Invalid type.')
                return False
        pywikibot.log('\u2192{} = {}'.format(key, config[key]))
    if sorted(has_keys) != sorted(required_keys):
        pywikibot.log('Missing one more required keys.')
        return False
    if 'BS_templates' not in config:
        config['BS_templates'] = dict()
    if 'railway_track_templates' not in config:
        config['railway_track_templates'] = set()
    if 'routemap_templates' not in config:
        config['routemap_templates'] = set()
    if not (config['BS_templates'] or config['railway_track_templates']
            or config['routemap_templates']):
        pywikibot.log('Missing templates.')
        return False
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


def mask_text(text, regex, mask=None):
    """
    Mask text using a regex.

    @rtype: str, dict
    """
    mask = mask or dict()
    try:
        key = max(mask.keys()) + 1
    except ValueError:
        key = 1
    matches = [match[0] if isinstance(match, tuple) else match
               for match in regex.findall(text)]
    matches = sorted(matches, key=len, reverse=True)
    for match in matches:
        mask[key] = match
        text = text.replace(match, '***bot***masked***{}***'.format(key))
        key += 1
    return text, mask


def unmask_text(text, mask):
    """Unmask text."""
    text = text.replace('|***bot***=***param***|', '{{!}}')
    while text.find('***bot***masked***') > -1:
        for key, value in mask.items():
            text = text.replace('***bot***masked***{}***'.format(key), value)
    return text


def mask_html_tags(text, mask=None):
    """Mask HTML tags."""
    tags_regex = re.compile(
        r'''(<\/?\w+(?:\s+\w+(?:\s*=\s*(?:(?:"[^"]*")|(?:'[^']*')|'''
        r'''[^>\s]+))?)*\s*\/?>)''',
        flags=re.S
    )
    return mask_text(text, tags_regex, mask)


def mask_pipe_mw(text):
    """Mask the pipe magic word ({{!}})."""
    return text.replace('{{!}}', '|***bot***=***param***|')


def get_bsicon_name(file):
    """
    Return the BSicon name.

    @param file: The file
    @type file: L{pywikibot.FilePage}

    @rtype: str
    """
    return os.path.splitext(os.path.basename(file.title(
        withNamespace=False)))[0][7:]


def standardize_bsicon_name(bsicon_name):
    """
    Return the standardized BSicon name.

    @param bsicon_name: BSicon name
    @type bsicon_name: str

    @rtype: str
    """
    if bsicon_name.find('&') > -1:
        bsicon_name = html_unescape(bsicon_name)
    if bsicon_name.find('%') > -1:
        bsicon_name = url_unquote(bsicon_name)
    if bsicon_name.find('_') > -1:
        bsicon_name = bsicon_name.replace('_', ' ')
    return bsicon_name


class BSiconsReplacer(MultipleSitesBot, FollowRedirectPageBot,
                      ExistingPageBot):
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
            'config': dict(),
            'local_config': None
        })
        self.generator = generator
        super().__init__(**kwargs)
        self._config = dict()
        self._disabled = set()

    @property
    def site_disabled(self):
        """True if the task is disabled on the site."""
        site = self.current_page.site
        if site in self._disabled:
            return True
        if not site.logged_in():
            site.login()
        page = pywikibot.Page(
            site,
            'User:{username}/shutoff/{class_name}.css'.format(
                username=site.user(),
                class_name=self.__class__.__name__
            )
        )
        if page.exists():
            content = page.get(force=True).strip()
            if content:
                pywikibot.warning('{} disabled on {}:\n{}'.format(
                    self.__class__.__name__, site, content))
                self._disabled.add(site)
                return True
        return False

    @property
    def site_config(self):
        """Return the site configuration."""
        site = self.current_page.site
        if site not in self._config:
            self._config[site] = copy.deepcopy(self.getOption('config'))
            self._config[site].update(get_json_from_page(pywikibot.Page(
                site, self.getOption('local_config'))))
            if not validate_local_config(self._config[site], site):
                pywikibot.error('Invalid config for {}.'.format(site))
                self._config[site] = None
        return self._config[site]

    def treat_page(self):
        """Process one page."""
        if not self.site_config or self.site_disabled:
            return
        text, mask = mask_html_tags(self.current_page.text)
        text = mask_pipe_mw(text)
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
        replacements = set()
        for tpl in wikicode.ifilter_templates():
            if tpl.name.matches(self.site_config['routemap_templates']):
                for param in tpl.params:
                    if not re.search(r'^(?:map\d*|\d+)$',
                                     str(param.name).strip()):
                        continue
                    param_value = str(param.value)
                    matches = ROUTEMAP_BSICON.findall(param_value)
                    if not matches:
                        continue
                    for match in matches:
                        current_icon = standardize_bsicon_name(
                            HTML_COMMENT.sub('', match[1]).strip())
                        new_icon = self.getOption('bsicons_map').get(
                            current_icon, None)
                        if not new_icon:
                            continue
                        param_value = param_value.replace(
                            ''.join(match),
                            match[0] + match[1].replace(current_icon, new_icon)
                            + match[2]
                        )
                        replacements.add('\u2192'.join([current_icon,
                                                        new_icon]))
                    param.value = param_value
            elif tpl.name.matches(self.site_config['railway_track_templates']):
                # Written for [[:cs:Template:Železniční trať]].
                for param in tpl.params:
                    param_value = HTML_COMMENT.sub('',
                                                   str(param.value)).strip()
                    if param.name.matches('typ'):
                        if param_value[:2] == 'ex':
                            current_icon = 'exl' + param_value[2:]
                        else:
                            current_icon = 'l' + param_value
                    else:
                        current_icon = param_value
                    current_icon = standardize_bsicon_name(current_icon)
                    new_icon = self.getOption('bsicons_map').get(current_icon,
                                                                 None)
                    if not new_icon:
                        continue
                    if param.name.matches('typ'):
                        if new_icon[:3] == 'exl':
                            replacement = 'ex' + new_icon[3:]
                        elif new_icon[:1] == 'l':
                            replacement = new_icon[1:]
                        else:
                            pywikibot.log('{} cannot be used in |typ=.'
                                          .format(new_icon))
                            continue
                    else:
                        replacement = new_icon
                    param.value = str(param.value).replace(param_value,
                                                           replacement)
                    replacements.add('\u2192'.join([current_icon, new_icon]))
            else:
                for icon_prefix, tpl_titles in self.site_config[
                        'BS_templates'].items():
                    if not tpl.name.matches(tpl_titles):
                        continue
                    for param in tpl.params:
                        if param.name.matches('1'):
                            prefix = icon_prefix.strip()
                        else:
                            prefix = ''
                        param_value = HTML_COMMENT.sub(
                            '', str(param.value)).strip()
                        current_icon = standardize_bsicon_name(
                            prefix + param_value)
                        new_icon = self.getOption('bsicons_map').get(
                            current_icon, None)
                        if not new_icon:
                            continue
                        # The replacement must have the same prefix.
                        if new_icon[:len(prefix)] == prefix:
                            param.value = str(param.value).replace(
                                param_value, new_icon[len(prefix):])
                            replacements.add('\u2192'.join([current_icon,
                                                            new_icon]))
        self.put_current(
            unmask_text(str(wikicode), mask),
            summary='{}: {}'.format(self.site_config['summary_prefix'],
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
        if arg in 'config' 'local_config':
            if not value:
                value = pywikibot.input(
                    'Please enter a value for {}'.format(arg),
                    default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if 'config' not in options:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    elif 'local_config' not in options:
        options['local_config'] = options['config']
    config = get_json_from_page(pywikibot.Page(
        site, options.pop('config')))
    if validate_config(config, site):
        options['config'] = config
    else:
        pywikibot.error('Invalid config.')
        return False

    bsicons_map = dict()
    pages = set()
    for page in options['config'].pop('redirects'):
        # Must be a BSicon redirect.
        if not (page.isRedirectPage() and
                isinstance(page, pywikibot.FilePage) and
                page_is_bsicon(page)):
            continue
        # Target must be a file.
        try:
            replacement = pywikibot.FilePage(page.getRedirectTarget())
        except (pywikibot.IsNotRedirectPage, ValueError) as e:
            pywikibot.warning(e)
            continue
        # Target must be a BSicon.
        if not page_is_bsicon(replacement):
            continue
        bsicon_name = get_bsicon_name(page)
        target_bsicon_name = get_bsicon_name(replacement)
        bsicons_map[bsicon_name] = target_bsicon_name
        if bsicon_name.find(' ') > -1:
            bsicons_map[bsicon_name.replace(' ', '_')] = target_bsicon_name
        pages = pages.union(page.globalusage())
    for key, value in options['config'].pop('replacement_map',
                                            dict()).items():
        try:
            page = pywikibot.FilePage(site, key)
            replacement = pywikibot.FilePage(site, value)
        except ValueError as e:
            pywikibot.warning(e)
            continue
        # Both must be BSicons.
        if not (page_is_bsicon(page) and page_is_bsicon(replacement)):
            continue
        bsicon_name = get_bsicon_name(page)
        target_bsicon_name = get_bsicon_name(replacement)
        bsicons_map[bsicon_name] = target_bsicon_name
        pages = pages.union(page.globalusage())
    if pages:
        options['bsicons_map'] = bsicons_map
        gen = (page for page in pages)
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = BSiconsReplacer(gen, **options)
        bot.run()


if __name__ == "__main__":
    main()
