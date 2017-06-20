#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Task   : Update page with Wikimedia Commons picture of the day
Author : JJMC89


The following parameters are supported:

&params;
"""
from __future__ import absolute_import, unicode_literals

__version__ = '$Id$'

import datetime
import re
import pywikibot
from pywikibot import pagegenerators
from pywikibot.bot import (MultipleSitesBot, ExistingPageBot, NoRedirectPageBot)

docuReplacements = {
    '&params;': pagegenerators.parameterHelp
}


def get_template_parameter_value(page, template, parameter):
    """
    Return the value of the template parameter from the page
    @param page: the page to parse
    @type page: page
    @param template: title of the template
    @type template: unicode
    @param parameter: parameter name
    @type parameter: unicode
    """
    # TODO: Search for redirects to the specified template
    parameterValue = u''
    if page.exists():
        for (foundTemplate, foundParameters) in pywikibot.textlib.extract_templates_and_params(page.get(), remove_disabled_parts=True, strip=True):
            if foundTemplate == template and foundParameters.has_key(parameter):
                parameterValue = foundParameters.get(parameter)
    else:
        pywikibot.warning(u'%s does not exist' % page.title(asLink=True))
    return parameterValue


class CommonsPotdImporter(MultipleSitesBot, ExistingPageBot, NoRedirectPageBot):
    def __init__(self, generator, **kwargs):
        """
        Constructor.
        @param generator: the page generator that determines on which pages
            to work
        @type generator: generator
        """
        self.generator = generator
        super(CommonsPotdImporter, self).__init__(**kwargs)

    def treat_page(self):
        commons = pywikibot.Site(code = u'commons', fam = u'commons')
        today = datetime.date.today()
        # fileTemplate = pywikibot.Page(commons, u'Template:Potd filename')
        # captionTemplate = pywikibot.Page(commons, u'Template:Potd description') # (Potd page, POTD description)
        filePage = pywikibot.Page(commons, u'Template:Potd/%s' % today.isoformat())
        file = get_template_parameter_value(filePage, u'Potd filename', u'1')
        # TODO: use languages instead of lang
        captionPage = pywikibot.Page(commons, u'Template:Potd/%s (%s)'
            % (today.isoformat(), self.current_page.site.lang))
        if self.current_page.site.lang != u'en' and not captionPage.exists():
            pywikibot.warning(u'%s does not exist' % captionPage.title(asLink=True))
            # try en instead
            captionPage = pywikibot.Page(commons, u'Template:Potd/%s (en)' % today.isoformat())
        caption = get_template_parameter_value(captionPage, u'Potd description', u'1')
        # TODO: Complete caption parsing to fix links (if not an interwiki then make it an interwiki to Commons)
        caption = re.sub(r"\[\[([^:])", r"[[:\1", caption, flags=re.UNICODE) # Force links to start with ':'
        caption = re.sub(r"\[\[(:Category:)", r"[[:c\1", caption, flags=re.UNICODE | re.IGNORECASE) # Make category links interwiki links
        # TODO: Use [[d:Q4608595]] to get the local {{Documentation}}
        doc = u'Documentation'
        if file != u'':
            summary = u'Updating Commons picture of the day'
            if caption != u'':
                summary = summary + u', [[:c:%s|caption attribution]]' % captionPage.title()
            else:
                summary = summary + u', failed to parse caption'
                pywikibot.error(u'Failed to parse parameter 1 from {{Potd description}} on %s'
                    % captionPage.title(asLink=True))
            self.put_current(u'<includeonly>{{#switch:{{{1|}}}|caption=%s|#default=%s}}</includeonly><noinclude>\n{{%s}}</noinclude>'
                % (caption, file, doc), summary=summary, minor=False)
        else:
            pywikibot.error(u'Failed to parse parameter 1 from {{Potd filename}} on %s'
                % filePage.title(asLink=True))


def main(*args):
    """
    Process command line arguments and invoke bot.
    If args is an empty list, sys.argv is used.
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
        options[option] = True
    gen = genFactory.getCombinedGenerator()
    if gen:
        gen = pagegenerators.PreloadingGenerator(gen)
        bot = CommonsPotdImporter(gen, **options)
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
