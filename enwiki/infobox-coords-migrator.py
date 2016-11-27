#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : Migrate deprecated infobox coordinates parameters
Author : JJMC89


The following parameters are required:

-config           The page title that has the JSON config (object)
                    The config must contain:
                      - initialReplacementTemplate (string)
                      - parametersMap (object of string/array)
                      - replacementParameterNames (string/array)
                      - template (string)
                    The config may optionally contain:
                      - editSummary (string)


The following parameters are supported:

&params;
"""
from __future__ import absolute_import, unicode_literals

__version__ = '$Id$'

import json
import re
import statistics
import sys
from collections import OrderedDict
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import (SingleSiteBot, ExistingPageBot, NoRedirectPageBot)

docuReplacements = {
    '&params;': pagegenerators.parameterHelp
}


def validate_config(config):
    """
    Validate the configuration and return bool
    @param config: configuration to validate
    @type config: dict
    """
    requiredKeys = [
      'initialReplacementTemplate',
      'parametersMap',
      'replacementParameterNames',
      'template'
    ]
    configKeys = []
    
    if not isinstance(config, dict):
        return False
    
    for key, value in config.items():
        if key == 'initialReplacementTemplate':
            if isinstance(value, str):
                if key in requiredKeys:
                    configKeys.append(key)
            else:
                return False
        elif key == 'parametersMap':
            if not isinstance(value, dict):
                return False
            for k, v in value.items():
                if not isinstance(k, str):
                    return False
                if isinstance(v, str):
                    value[k] = [v]
                elif isinstance(v, list):
                    for i in v:
                        if not isinstance(i, str):
                            return False
                else:
                    return False
            if key in requiredKeys:
                configKeys.append(key)
        elif key == 'replacementParameterNames':
            if isinstance(value, str):
                config[key] = [value]
            elif isinstance(value, list):
                for name in value:
                    if not isinstance(name, str):
                        return False
            else:
                return False
            if key in requiredKeys:
                configKeys.append(key)
        elif key == 'template':
            template = pywikibot.Page(pywikibot.Site(),
              u'Template:%s' % value)
            if not template.isRedirectPage():
                config[key] = template
                if key in requiredKeys:
                    configKeys.append(key)
            else:
                return False
        elif key == 'editSummary':
            if value is None or isinstance(value, str):
                if key in requiredKeys:
                    configKeys.append(key)
            else:
                return False
        else:
            return False
    
    if sorted(configKeys) != sorted(requiredKeys):
        return False
    
    return True


class InfoboxCoordinatesParametersMigrator(
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
          'editSummary': None,
          'initialReplacementTemplate': None,
          'parametersMap': None,
          'replacementParameterNames': None,
          'template': None
        })
        
        self.generator = generator
        super(InfoboxCoordinatesParametersMigrator, self).__init__(
          site=True, **kwargs)
          
        self.HTMLComment = re.compile(r'<!--.*?-->', flags=re.DOTALL)
        
        self.initialReplacementParameterValue = (
          mwparserfromhell.nodes.Template(
          self.getOption('initialReplacementTemplate').strip()))
        self.parametersMap = self.getOption('parametersMap')
        self.replacementParameterNames = self.getOption(
          'replacementParameterNames')
        self.template = self.getOption('template')
        self.templateTitles = [self.template.title(withNamespace=False)]
        for tpl in self.template.backlinks(
          filterRedirects=True,
          namespaces=self.site.namespaces.TEMPLATE
        ):
            self.templateTitles.append(tpl.title(withNamespace=False))
        summary = self.getOption('editSummary')
        if summary is None:
            self.summary = (
              u'Migrate {{%s}} coordinates parameters to {{Coord}}, '
              u'see [[Wikipedia:Coordinates in infoboxes]]' %
                self.template.title(withNamespace=False)
            )
        else:
            self.summary = summary.strip()
    
    def check_enabled(self):
        """Test if the task is enabled"""
        page = pywikibot.Page(self.site,
          u'User:%s/shutoff/%s' % (self.site.user(), self.__class__.__name__))
        if page.exists():
            content = page.get().strip()
            if content != u'':
                sys.exit(u'Task disabled:\n%s' % content)
    
    def get_replacement_parameter_spaces(self, templateText, parameterName):
        """
        Determine template spacing and return spaces for between the
          replacement parameter name and the =
        @param templateText: template text to parse
        @type templateText: str
        """
        # Remove parameter values so that the regex doesn't match in them.
        wikicode = mwparserfromhell.parse(templateText.strip())
        tpl = wikicode.filter_templates(recursive=False)[0]
        for param in tpl.params:
            tpl.remove(param, keep_field=True)
        
        matches = re.findall(
          r'\n\s*\|\s*(\S+)(\s*)=',
          str(wikicode)
        )
        
        if matches:
            spaces = [(len(spaces) > 1) for param, spaces in matches]
            if max(spaces):
                fullParamLens = [(len(param) + len(spaces))
                  for param, spaces in matches]
                try:
                    fullParamLen = statistics.mode(fullParamLens)
                except statistics.StatisticsError:
                    fullParamLen = statistics.median_high(fullParamLens)
                return max(fullParamLen - len(parameterName), 1) * u' '
        
        return u' '
    
    def treat_page(self):
        self.check_enabled()
        skip = False
        text = self.current_page.get().strip()
        wikicode = mwparserfromhell.parse(text)
        replacementParameterValue = mwparserfromhell.nodes.Template(
          self.getOption('initialReplacementTemplate').strip())
        
        for tpl in wikicode.filter_templates():
            if tpl.name.matches(self.templateTitles):
                replacementParameterName = None
                before = None
                
                for parameterName in self.replacementParameterNames:
                    if tpl.has(parameterName):
                        parameterValue = self.HTMLComment.sub(u'',
                          str(tpl.get(parameterName).value)).strip()
                        if parameterValue != u'':
                            skip = True
                            print(u'Non-empty replacement parameter: %s=%s'
                              % (parameterName, parameterValue))
                        elif replacementParameterName is None:
                            replacementParameterName = parameterName
                if replacementParameterName is None:
                    replacementParameterName = (
                      self.replacementParameterNames[0])
                
                spaces = self.get_replacement_parameter_spaces(str(tpl),
                  replacementParameterName)
                
                for key, value in self.parametersMap.items():
                    for param in value:
                        if tpl.has(param):
                            if before is None:
                                before = param
                            paramValue = self.HTMLComment.sub(u'',
                              str(tpl.get(param).value)).strip()
                            if paramValue != u'':
                                replacementParameterValue.add(key, paramValue)
                                # Only take the first alias with a value
                                break
                
                if (str(replacementParameterValue)
                  != str(self.initialReplacementParameterValue)
                ):
                    tpl.add(
                      replacementParameterName,
                      replacementParameterValue,
                      before=before
                    )
                
                for params in self.parametersMap.values():
                    for param in params:
                        if tpl.has(param):
                            tpl.remove(param)
                
                # There should be only one match per page,
                # so break the loop for speed.
                break
        
        newtext = str(wikicode).strip()
        if not skip and newtext != text:
            # Fix spacing for the replacement parameter.
            newtext = re.sub(
              r'\n?([ \t]*\|\s*%s)\s*=\s*(%s)\s*(\||\}\})' % (
                  re.escape(replacementParameterName),
                  re.escape(str(replacementParameterValue))
                ),
              r'\n\1%s= \2\n\3' % spaces,
              newtext
            )
            self.put_current(newtext, summary=self.summary, minor=False)
        else:
            print(u'Skipping %s' % self.current_page.title(asLink=True))


def main(*args):
    """
    Process command line arguments and invoke bot.
    @param args: command line arguments
    @type args: list of unicode
    """
    options = {}
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    genFactory = pagegenerators.GeneratorFactory()
    # Parse command line arguments
    for arg in local_args:
        if genFactory.handleArg(arg):
            continue
        arg, sep, value = arg.partition(':')
        option = arg[1:]
        if option in ('config'):
            if not value:
                value = pywikibot.input('Please enter a value for %s' % arg,
                  default=None)
            options[option] = value
        else:
            options[option] = True
    gen = genFactory.getCombinedGenerator()
    if 'config' not in options:
        pywikibot.bot.suggest_help(missing_parameters=['config'])
        return False
    else:
        config = pywikibot.Page(pywikibot.Site(), options['config']).get()
        del options['config']
        config = json.loads(config, object_pairs_hook=OrderedDict)
        if validate_config(config):
            options.update(config)
        else:
            pywikibot.bot.suggest_help(
              additional_text='The specified configuration is invalid.')
            return False
        if gen:
            gen = pagegenerators.PreloadingGenerator(gen)
            bot = InfoboxCoordinatesParametersMigrator(gen, **options)
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
