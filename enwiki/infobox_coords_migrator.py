#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task   : Migrate deprecated infobox coordinates parameters
Author : JJMC89


The following parameters are required:

-config           The page title that has the JSON config (object)
                    The config must contain:
                      - coordinatesSets (object)
                        - initialReplacementTemplate (string)
                        - parametersDefaults (optional; object of string)
                        - parametersMap (object of string/array)
                        - replacementParameterNames (string/array)
                      - template (string)
                    The config may optionally contain:
                      - editSummary (string)
                      - keepParameters (string/array)


The following parameters are supported:

-always           Don't prompt to save changes.

&params;
"""
# pylint: disable=all
import json
import re
import statistics
import sys
from collections import OrderedDict
import mwparserfromhell
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import SingleSiteBot, ExistingPageBot, NoRedirectPageBot

docuReplacements = {
    '&params;': pagegenerators.parameterHelp
}

HTMLCOMMENT = re.compile(r'<!--.*?-->', flags=re.DOTALL)


def validate_config(config):
    """
    Validate the configuration and return bool.

    @param config: configuration to validate
    @type config: dict
    @rtype: bool
    """
    if not isinstance(config, dict):
        return False
    requiredKeys = [
        'coordinatesSets',
        'template'
    ]
    hasKeys = []
    for key, value in config.items():
        if key in requiredKeys:
            hasKeys.append(key)
        if key == 'coordinatesSets':
            if not isinstance(value, list):
                return False
            for coordinatesSet in value:
                if not isinstance(coordinatesSet, dict):
                    return False
                requiredKeys2 = [
                    'initialReplacementTemplate',
                    'parametersMap',
                    'replacementParameterNames'
                ]
                hasKeys2 = []
                for key2, value2 in coordinatesSet.items():
                    if key2 in requiredKeys2:
                        hasKeys2.append(key2)
                    if key2 == 'initialReplacementTemplate':
                        if not isinstance(value2, str):
                            return False
                    elif key2 == 'parametersMap':
                        if not isinstance(value2, dict):
                            return False
                        for key3, value3 in value2.items():
                            if isinstance(value3, str):
                                value2[key3] = [value3]
                            elif isinstance(value3, list):
                                for item in value3:
                                    if not isinstance(item, str):
                                        return False
                            else:
                                return False
                    elif key2 == 'replacementParameterNames':
                        if isinstance(value2, str):
                            coordinatesSet[key2] = [value2]
                        elif isinstance(value2, list):
                            for name in value2:
                                if not isinstance(name, str):
                                    return False
                        else:
                            return False
                    elif key2 == 'parametersDefaults':
                        if not isinstance(value2, dict):
                            return False
                        for key3, value3 in value2.items():
                            if not isinstance(value3, str):
                                return False
                    else:
                        return False
                if sorted(hasKeys2) != sorted(requiredKeys2):
                    return False
        elif key == 'keepParameters':
            if isinstance(value, str):
                config[key] = [value]
            elif not isinstance(value, list):
                return False
        elif key == 'template':
            template = pywikibot.Page(pywikibot.Site(),
                                      'Template:%s' % value)
            if not template.isRedirectPage():
                config[key] = template
                print('\n== %s ==' % template.title(asLink=True))
            else:
                return False
        elif key == 'editSummary':
            if not (value is None or isinstance(value, str)):
                return False
        else:
            return False
    if sorted(hasKeys) != sorted(requiredKeys):
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
            'coordinatesSets': None,
            'editSummary': None,
            'keepParameters': [],
            'template': None
        })

        self.generator = generator
        super(InfoboxCoordinatesParametersMigrator, self).__init__(
            site=True, **kwargs)

        self.coordinatesSets = self.getOption('coordinatesSets')
        self.template = self.getOption('template')
        self.keepParameters = self.getOption('keepParameters')
        self.templateTitles = [self.template.title(withNamespace=False),
                               self.template.title(underscore=True,
                                                   withNamespace=False)]
        for tpl in self.template.backlinks(
            filterRedirects=True,
            namespaces=self.site.namespaces.TEMPLATE
        ):
            self.templateTitles.append(tpl.title(withNamespace=False))
            self.templateTitles.append(
                tpl.title(underscore=True, withNamespace=False))
        summary = self.getOption('editSummary')
        if summary is None:
            self.summary = (
                'Migrate {{%s}} coordinates parameters to {{Coord}}, '
                'see [[Wikipedia:Coordinates in infoboxes]]' %
                self.template.title(withNamespace=False)
            )
        else:
            self.summary = summary.strip()
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

    def get_replacement_parameter_spaces(self, templateText, parameterName):
        """
        Determine template spacing and return a tuple of spaces before the pipe
        and spaces before the =

        @param templateText: template text to parse
        @type templateText: str
        @param parameterName: parameter name
        @type parameterName: str
        @rtype: tuple
        """
        wikicode = mwparserfromhell.parse(
            templateText.strip(),
            skip_style_tags=True
        )
        tpl = wikicode.filter_templates(recursive=False)[0]
        # Remove parameter values so that the regex doesn't match in them.
        for param in tpl.params:
            tpl.remove(param, keep_field=True)
        matches = re.findall(r'\n( *)\|\s*(\S+)(\s*)=', str(wikicode))
        if matches:
            beforePipeSpacesLen = [len(match[0]) for match in matches]
            try:
                beforePipe = statistics.mode(beforePipeSpacesLen) * ' '
            except statistics.StatisticsError:
                beforePipe = statistics.median_low(beforePipeSpacesLen) * ' '
            hasSpacesBeforeEquals = [(len(match[2]) > 1) for match in matches]
            if max(hasSpacesBeforeEquals):
                fullParamLens = [(len(match[1]) + len(match[2]))
                                 for match in matches]
                try:
                    fullParamLen = statistics.mode(fullParamLens)
                except statistics.StatisticsError:
                    fullParamLen = statistics.median_high(fullParamLens)
                beforeEquals = max(fullParamLen - len(parameterName), 1) * ' '
            else:
                beforeEquals = ' '
            return (beforePipe, beforeEquals)
        return ('', ' ')

    def treat_page(self):
        self.check_enabled()

        skipPage = True
        spacingFixNeeded = []
        text = self.current_page.get().strip()
        wikicode = mwparserfromhell.parse(text, skip_style_tags=True)

        # Loop over all templates on the page.
        for tpl in wikicode.filter_templates():
            if not tpl.name.matches(self.templateTitles):
                continue

            keepParameters = list(self.keepParameters)
            removeParameters = []

            # Loop over each set of coordinates.
            for coordinatesSet in self.coordinatesSets:

                before = None
                parametersMap = coordinatesSet.get('parametersMap')
                replacementParameterName = None
                replacementParameterNames = (
                    coordinatesSet.get('replacementParameterNames'))
                replacementParameterValue = mwparserfromhell.nodes.Template(
                    coordinatesSet.get('initialReplacementTemplate').strip())
                skipCoordinatesSet = False

                # Determine the replacement parameter name.
                for parameterName in replacementParameterNames:
                    if tpl.has(parameterName):
                        parameterValue = HTMLCOMMENT.sub(
                            '',
                            str(tpl.get(parameterName).value)).strip()
                        if parameterValue:
                            skipCoordinatesSet = True
                            print('* %s has {{para|%s|<nowiki>%s</nowiki>}}'
                                  % (
                                      self.current_page.title(asLink=True),
                                      parameterName,
                                      parameterValue
                                  ))
                        elif replacementParameterName is None:
                            replacementParameterName = parameterName
                if replacementParameterName is None:
                    replacementParameterName = replacementParameterNames[0]

                if skipCoordinatesSet:
                    # Do not remove these parameters.
                    for params in parametersMap.values():
                        for param in params:
                            if tpl.has(param):
                                paramValue = HTMLCOMMENT.sub(
                                    '',
                                    str(tpl.get(param).value)).strip()
                                if paramValue:
                                    keepParameters.append(param)
                    continue

                skipPage = False

                # Map dperecated paramters into the replacement.
                for key, value in parametersMap.items():
                    for param in value:
                        if tpl.has(param):
                            if before is None:
                                before = param
                            paramValue = HTMLCOMMENT.sub(
                                '',
                                str(tpl.get(param).value)).strip()
                            if paramValue:
                                replacementParameterValue.add(key, paramValue)
                                # Only take the first alias with a value.
                                break

                # Slate parameters for removal.
                for params in parametersMap.values():
                    for param in params:
                        if tpl.has(param):
                            removeParameters.append(param)

                # Add the replacement parameter.
                if (str(replacementParameterValue).strip() != (
                        '{{%s}}' % coordinatesSet.get(
                            'initialReplacementTemplate').strip())):
                    if 'parametersDefaults' in coordinatesSet:
                        for key, value in (coordinatesSet.get(
                                'parametersDefaults').items()):
                            if not replacementParameterValue.has(key):
                                replacementParameterValue.add(key, value)
                    spacingFixNeeded.append((
                        replacementParameterName,
                        str(replacementParameterValue),
                        self.get_replacement_parameter_spaces(
                            str(tpl),
                            replacementParameterName
                        )
                    ))
                    tpl.add(
                        replacementParameterName,
                        replacementParameterValue,
                        before=before
                    )

            # Remove the mapped parameters.
            for param in set(removeParameters) - set(keepParameters):
                tpl.remove(param)

        newtext = str(wikicode).strip()
        if not skipPage and newtext != text:
            # Fix spacing for the replacement parameters.
            for tup in spacingFixNeeded:
                newtext = re.sub(
                    r'\n?[ \t]*(\|\s*%s)\s*=\s*(%s)\s*(\||\}\})' % (
                        re.escape(tup[0]),
                        re.escape(tup[1])
                    ),
                    r'\n%s\1%s= \2\n%s\3' % (tup[2][0], tup[2][1], tup[2][0]),
                    newtext
                )
            self.put_current(newtext, summary=self.summary, minor=False)


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
        if option in ('config'):
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
    config = pywikibot.Page(pywikibot.Site(), options.pop('config')).get()
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
