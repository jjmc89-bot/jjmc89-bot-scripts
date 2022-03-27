"""
Reports and notifies inactive admins.

The following parameters are required:

-config           The page title that has the JSON config (object)

The following parameters are supported:

-max_attempts     The maximum number of attempts to notify (default: 3)
"""
from __future__ import annotations

import json
import re
from contextlib import suppress
from datetime import date

import mwparserfromhell
import pywikibot
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta


def get_json_from_page(page):
    """
    Return JSON from the page.

    :param page: Page to read
    :type page: pywikibot.Page

    :rtype: dict
    """
    if page.isRedirectPage():
        pywikibot.log(f"{page!r} is a redirect.")
        page = page.getRedirectTarget()
    if not page.exists():
        pywikibot.log(f"{page!r} does not exist.")
        return {}
    try:
        return json.loads(page.get().strip())
    except ValueError:
        pywikibot.error(f"{page!r} does not contain valid JSON.")
        raise
    except pywikibot.exceptions.PageRelatedError:
        return {}


def validate_options(options):
    """
    Validate the options and return bool.

    :param options: options to validate
    :type options: dict

    :rtype: bool
    """
    pywikibot.log("Options:")
    notice_keys = [
        "email_subject",
        "email_subject2",
        "email_text",
        "email_text2",
        "note_summary",
        "note_summary2",
        "note_text",
        "note_text2",
    ]
    required_keys = notice_keys + ["date", "exclusions"]
    has_keys = []
    result = True
    for key, value in options.items():
        pywikibot.log(f"-{key} = {value}")
        if key in required_keys:
            has_keys.append(key)
        if key == "date":
            if not isinstance(value, date):
                result = False
        elif key == "exclusions":
            if isinstance(value, str):
                options[key] = [value]
            elif not isinstance(value, list):
                result = False
            else:
                for item in value:
                    if not isinstance(item, str):
                        result = False
        elif key == "max_attempts":
            try:
                options[key] = int(value)
            except ValueError:
                result = False
        elif key in notice_keys:
            if not isinstance(value, str):
                result = False
        else:
            result = False
        pywikibot.log(f"\u2192{key} = {options[key]}")
    if sorted(has_keys) != sorted(required_keys):
        result = False
    return result


def get_inactive_users(cutoff, exclusions, group=None, site=None):
    """
    Get a set of inactive users.

    :param exclusions: List of users to exclude
    :type exclusions: list
    :param site: site to work on
    :type site: pywikibot.APISite
    :param group: only include users that are members of this group
    :type group: str

    :rtype: set
    """
    users = set()
    if not site:
        site = pywikibot.Site()
    for user_dict in site.allusers(group=group):
        name = user_dict["name"]
        if name not in exclusions:
            user = User(site, name)
            if not user.is_active(cutoff=cutoff):
                users.add(user)
    return users


def create_section(options, site=None):
    """
    Create a section of inactive admins and notify them.

    :param options: Bot options
    :type options: dict

    :rtype: str
    """
    inactive_sysops = get_inactive_users(
        options["date"] + relativedelta(years=-1),
        options["exclusions"],
        site=site,
        group="sysop",
    )
    text = f"=== {options['date']:%B %Y} ===\n"
    if inactive_sysops:
        text += (
            "{{{{hatnote|Administrators listed below may have their "
            "permissions removed on or after {date.day} {date:%B %Y} (UTC)"
            " after being duly notified.}}}}\n{{{{iarow/t}}}}\n".format_map(
                options
            )
        )
        for user in inactive_sysops:
            tpl = mwparserfromhell.nodes.Template("iarow")
            tpl.add("1", user.username)
            if user.last_edit:
                tpl.add(
                    "lastedit",
                    "{date.day} {date:%B %Y}".format(
                        date=user.last_edit[2].date()
                    ),
                )
            if user.last_event:
                tpl.add(
                    "lastlog",
                    "{date.day} {date:%B %Y}".format(
                        date=user.last_event.timestamp().date()
                    ),
                )
            user.notify(options)
            for param, value in user.notifications.items():
                if value:
                    tpl.add(param, value)
            text += str(tpl) + "\n"
        text += "{{iarow/b}}"
    else:
        text += ": None"
    text += "\n\n"
    return text


def update_section(text, options, site=None):
    """
    Update the specified section.

    Active admins are removed and second notifications sent one week
    before the date in the section.

    :param text: Text of the section
    :type text: str
    :param options: Bot options
    :type options: dict

    :rtype: str
    """
    if not site:
        site = pywikibot.Site()
    wikicode = mwparserfromhell.parse(text, skip_style_tags=True)
    if not wikicode.filter_templates(recursive=False, matches="iarow"):
        pywikibot.log("No inactive admins.")
        return text
    inactive_sysops = 0
    match = re.match(
        r".+?on or after \b(?P<date>.+?) \(UTC\)", text, flags=re.S
    )
    if match:
        section_date = parse(match.group("date")).date()
    else:
        raise ValueError("Could not find a valid date.")
    for tpl in wikicode.ifilter_templates(recursive=False):
        if not tpl.name.matches("iarow"):
            continue
        if not tpl.has("1", ignore_empty=True):
            pywikibot.log(f"{tpl} has no user specified")
            wikicode.remove(tpl)
            continue
        user = User(site, tpl.get("1"))
        if "sysop" not in user.groups():
            pywikibot.log(f"{user!r} is not a sysop.")
            wikicode.remove(tpl)
        elif user.is_active(cutoff=section_date + relativedelta(years=-1)):
            pywikibot.log(f"{user!r} is now active.")
            wikicode.remove(tpl)
        else:
            inactive_sysops += 1
            if section_date + relativedelta(weeks=-1) == date.today():
                for param, value in user.notifications.items():
                    if tpl.has(param, ignore_empty=True):
                        user.notifications[param] = value
                user.notify(options, notice_number=2)
                for param, value in user.notifications.items():
                    if value and not tpl.has(param, ignore_empty=True):
                        tpl.add(param, value)
    if inactive_sysops == 0:
        for tpl in wikicode.ifilter_templates(
            recursive=False, matches="iarow"
        ):
            wikicode.remove(tpl)
        text = str(wikicode) + "\n: None\n"
    else:
        text = str(wikicode)
    return re.sub(r"\n{2,}", r"\n", text) + "\n"


def split_into_sections(text):
    """
    Split wikitext into sections based on any level wiki heading.

    :param text: Text to split
    :type text: str

    :rtype: list
    """
    headings_regex = re.compile(
        r"^={1,6}.*?={1,6}(?: *<!--.*?-->)?\s*$", flags=re.M
    )
    sections = []
    last_match_start = 0
    for match in headings_regex.finditer(text):
        match_start = match.start()
        if match_start > 0:
            sections.append(text[last_match_start:match_start])
            last_match_start = match_start
    sections.append(text[last_match_start:])
    return sections


class User(pywikibot.User):
    """Extend pywikibot.User."""

    def __init__(self, source, title=""):
        """
        Initialize.

        All parameters are the same as for pywikibot.User.
        """
        super().__init__(source, title)
        self._last_event = None
        self.notifications: dict[str, str | None] = {
            "email": None,
            "email2": None,
            "note": None,
            "diff": None,
            "note2": None,
            "diff2": None,
        }

    def is_active(self, cutoff=date.today() + relativedelta(years=-1)):
        """
        Return True if the user is active.

        A user is active if they have an edit or log entry since the cutoff.

        :param cutoff: Cutoff for user activity
        :type cutoff: datetime.date
        :rtype: bool
        """
        if self.last_edit and self.last_edit[2].date() >= cutoff:
            return True
        if self.last_event and self.last_event.timestamp().date() >= cutoff:
            return True
        return False

    @property
    def last_event(self):
        """
        Return the user's last log entry.

        :rtype: pywikibot.LogEntry or None
        """
        if self._last_event is not None:
            return self._last_event
        for logevent in self.site.logevents(user=self.username):
            try:
                le_action = logevent.action()
            except KeyError as e:
                pywikibot.log(e)
                continue
            else:
                if le_action != "create":
                    self._last_event = logevent
                    return self._last_event
        return None

    def notify(self, options, notice_number=1):
        """
        Notify the user.

        :param options: Bot options
        :type options: dict
        :param notice_number: Notice number
        :type notice_number: int
        """
        param_suffix = "" if notice_number == 1 else str(notice_number)
        if (
            self.notifications[f"note{param_suffix}"]
            or self.notifications[f"email{param_suffix}"]
        ):
            pywikibot.log(f"{self!r} has already been notified.")
            return
        talk_page = self.getUserTalkPage()
        success = False
        attempts = 0
        while not success and attempts < options.get("max_attempts"):
            attempts += 1
            with suppress(pywikibot.exceptions.Error):
                success = self.site.editpage(
                    talk_page,
                    summary=options[f"note_summary{param_suffix}"],
                    minor=False,
                    bot=False,
                    section="new",
                    text=options[f"note_text{param_suffix}"],
                )
            if not success:
                pywikibot.log(
                    f"Failed to send note{param_suffix} to {self!r}. Attempt: "
                    f"{attempts}."
                )
        if success:
            self.notifications[
                f"note{param_suffix}"
            ] = "{date.day} {date:%B %Y}".format(date=date.today())
            self.notifications[f"diff{param_suffix}"] = str(
                talk_page.latest_revision_id
            )
        if self.isEmailable():
            success = False
            attempts = 0
            while not success and attempts < options.get("max_attempts"):
                attempts += 1
                with suppress(pywikibot.exceptions.Error):
                    success = self.send_email(
                        options[f"email_subject{param_suffix}"],
                        options[f"email_text{param_suffix}"],
                    )
                if not success:
                    pywikibot.log(
                        f"Failed to send email{param_suffix} to {self!r}. "
                        f"Attempt: {attempts}."
                    )
            if success:
                self.notifications[
                    f"email{param_suffix}"
                ] = "{date.day} {date:%B %Y}".format(date=date.today())
        else:
            pywikibot.log(f"{self!r} has email disabled.")
            self.notifications[f"email{param_suffix}"] = "no"


def main(*args):
    """
    Process command line arguments and invoke bot.

    :param args: command line arguments
    :type args: list of unicode
    """
    options = {
        "date": date.today() + relativedelta(months=1),
        "exclusions": [],
        "max_attempts": 3,
    }
    # Process global arguments
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    site.login()
    # Parse command line arguments
    for arg in local_args:
        arg, _, value = arg.partition(":")
        arg = arg[1:]
        if arg in ("config", "max_attempts"):
            if not value:
                value = pywikibot.input(
                    f"Please enter a value for {arg}", default=None
                )
            options[arg] = value
        else:
            options[arg] = True
    if "config" not in options:
        pywikibot.bot.suggest_help(missing_parameters=["config"])
        return 1
    options.update(
        get_json_from_page(pywikibot.Page(site, options.pop("config")))
    )
    if not validate_options(options):
        pywikibot.error("Invalid options.")
        return 1
    page = pywikibot.Page(
        site, f"Wikipedia:Inactive administrators/{options['date']:%Y}"
    )
    sections = split_into_sections(page.text)
    section = None
    log_section = None
    for i, sect in enumerate(sections):
        sect_code = mwparserfromhell.parse(sect, skip_style_tags=True)
        heading = sect_code.filter(forcetype=mwparserfromhell.nodes.Heading)
        if not heading:
            continue
        heading = heading[0]
        if not log_section and heading.title.matches("Log"):
            log_section = i
        if heading.title.matches(f"{options['date']:%B %Y}"):
            section = sect
            break
    summary = f"/* {options['date']:%B %Y} */ "
    if section:
        page.text = page.text.replace(
            str(section), update_section(str(section), options, site=site)
        )
        summary += "Updating"
    else:
        current_page = pywikibot.Page(
            site,
            f"Wikipedia:Inactive administrators/{date.today():%Y}",
        )
        options["exclusions"].extend(  # type: ignore[attr-defined]
            user.username for user in current_page.linkedPages(namespaces=2)
        )
        section = create_section(options, site=site)
        if log_section:
            sections.insert(log_section + 1, section)
        else:
            sections.append(section)
        page.text = "".join(str(i) for i in sections)
        summary += "Reporting"
    summary += " inactive admins"
    page.save(summary=summary, minor=False, botflag=False, force=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
