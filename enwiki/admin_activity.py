"""Track admin activity and notify inactive admins."""
from __future__ import annotations

import argparse
import configparser
import datetime
import os.path
import re
from collections import defaultdict
from contextlib import suppress
from enum import IntEnum
from functools import cache, cached_property
from typing import TYPE_CHECKING, NamedTuple

import mwparserfromhell
import pymysql.cursors
import pywikibot
import pywikibot.config
import pywikibot.page
from dateutil.relativedelta import relativedelta
from pywikibot.bot import _GLOBAL_HELP
from pywikibot.logentries import LogEntry
from pywikibot.time import Timestamp
from pywikibot_extensions.page import Page


if TYPE_CHECKING:
    from collections.abc import Container, Mapping

    from pymysql.connections import Connection
    from pywikibot.site import APISite


C2_MIN_EDITS = 100
C2_RISK_EDITS = 50 * 5
NOW = Timestamp.utcnow()
TODAY = NOW.date()
NOW_MINUS_5Y = NOW + relativedelta(years=-5)
THIS_MONTH = Timestamp.combine(
    TODAY + relativedelta(day=1),
    datetime.time.min,
)
LAST_MONTH = THIS_MONTH + relativedelta(months=-1)
NEXT_MONTH = THIS_MONTH + relativedelta(months=1)
NEXT_MONTH_MINUS_12M = THIS_MONTH + relativedelta(months=-11)
THIS_MONTH_PLUS_3M = THIS_MONTH + relativedelta(months=3)
THIS_MONTH_MINUS_3M = THIS_MONTH + relativedelta(months=-3)
THIS_MONTH_MINUS_57M = THIS_MONTH + relativedelta(months=-57)
PKG_CONFIGS = [
    os.path.expanduser("~/.admin-activity.ini"),
    ".admin-activity.ini",
]
DB_CONFIGS = [
    os.path.expanduser("~/replica.my.cnf"),
    os.path.expanduser("~/.my.cnf"),
] + PKG_CONFIGS


class _DatabaseConfig(NamedTuple):
    user: str
    password: str
    database: str
    host: str
    port: int


class _NoteData(NamedTuple):
    id: int
    timestamp: Timestamp


class _Notification(IntEnum):
    C1N1 = 11
    C1N2 = 12
    C2R = 20
    C2N1 = 21
    C2N2 = 22


class _UserData(NamedTuple):
    id: int
    name: str
    last_rev_id: int | None
    last_rev_timestamp: Timestamp | None
    last_log_id: int | None
    last_log_timestamp: Timestamp | None
    c2_editcount: int
    c2_desysop_timestamp: Timestamp | None
    c2_risk_editcount: int
    sysop: bool
    bot: bool
    bureaucrat: bool


class User(pywikibot.page.User):
    """Extends pywikibot.page.User."""

    @cached_property
    def aliases(self) -> set[User]:
        """User's aliases."""
        aliases = _aliases().get(self.username, "")
        if not aliases:
            return set()
        return {User(self.site, i) for i in aliases.split("|")}

    @cached_property
    def c2_edits(self) -> int:
        """User's criterion 2 edits."""
        if self.database_data and self.database_data.c2_desysop_timestamp:
            c2_desysop_dtm = self.database_data.c2_desysop_timestamp
            if c2_desysop_dtm.date() <= TODAY:
                since = NOW_MINUS_5Y
            else:
                since = c2_desysop_dtm + relativedelta(years=-5)
        else:
            since = THIS_MONTH_MINUS_57M
        return self.minimum_edits_since(
            edits=C2_MIN_EDITS,
            since=since,
        )

    @cached_property
    def c2_notification(self) -> _Notification | None:
        """User's criterion 2 notification."""
        if self.database_data and self.database_data.c2_desysop_timestamp:
            c2_desysop_dt = self.database_data.c2_desysop_timestamp.date()
            if c2_desysop_dt <= TODAY:
                return None  # desysop pending
        else:
            c2_desysop_dt = THIS_MONTH_PLUS_3M.date()
        c2_first_note = self.last_notification(_Notification.C2N1)
        c2_second_note = self.last_notification(_Notification.C2N2)
        if (
            c2_second_note
            and c2_first_note
            and c2_second_note.timestamp < c2_first_note.timestamp
        ):
            c2_second_note = None
        if (
            c2_first_note
            and c2_first_note.timestamp.date() < THIS_MONTH_MINUS_3M.date()
        ):
            c2_first_note = None
        if (
            THIS_MONTH.date()
            <= c2_desysop_dt + relativedelta(months=-1)
            < THIS_MONTH.date() + relativedelta(weeks=1)
            and not c2_second_note
        ):
            return _Notification.C2N2
        if (
            THIS_MONTH.date()
            <= c2_desysop_dt + relativedelta(months=-3)
            < THIS_MONTH.date() + relativedelta(weeks=1)
            and not c2_first_note
        ):
            return _Notification.C2N1
        return None

    @cached_property
    def c2_risk_edits(self) -> int:
        """Edits for the low activity period."""
        return self.minimum_edits_since(
            edits=C2_RISK_EDITS,
            since=NOW_MINUS_5Y,
        )

    @cached_property
    def database_data(self) -> _UserData | None:
        """User's data from the database."""
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM `users` WHERE `user_id` = %s",
                self.userid,
            )
            result = cursor.fetchone()
        if not result:
            return None
        return _UserData(
            id=result["user_id"],
            name=result["user_name"],
            last_rev_id=result["user_last_rev_id"],
            last_rev_timestamp=Timestamp.set_timestamp(
                result["user_last_rev_timestamp"]
            )
            if result["user_last_rev_timestamp"]
            else None,
            last_log_id=result["user_last_log_id"],
            last_log_timestamp=Timestamp.set_timestamp(
                result["user_last_log_timestamp"]
            )
            if result["user_last_log_timestamp"]
            else None,
            c2_editcount=result["user_c2_editcount"],
            c2_desysop_timestamp=Timestamp.set_timestamp(
                result["user_c2_desysop_timestamp"]
            )
            if result["user_c2_desysop_timestamp"]
            else None,
            c2_risk_editcount=result["user_c2_risk_editcount"],
            sysop=bool(result["user_sysop"]),
            bot=bool(result["user_bot"]),
            bureaucrat=bool(result["user_bureaucrat"]),
        )

    @cached_property
    def _last_contrib(self) -> tuple[int, Timestamp] | None:
        last_live = self.last_edit
        last_deleted = next(self.deleted_contributions(total=1), None)
        if last_live and last_deleted:
            if last_live[2] > last_deleted[1].timestamp:
                return last_live[1], last_live[2]
            return last_deleted[1].revid, last_deleted[1].timestamp
        if last_live:
            return last_live[1], last_live[2]
        if last_deleted:
            return last_deleted[1].revid, last_deleted[1].timestamp
        return None

    @cached_property
    def last_contrib(self) -> tuple[int, Timestamp] | None:
        """User's last contribution."""
        last = self._last_contrib
        for alias in self.aliases:
            if alias.last_contrib is None:
                continue
            if last is None or alias.last_contrib[1] > last[1]:
                last = alias.last_contrib
        return last

    @cached_property
    def last_event(self) -> LogEntry | None:
        """User's last log entry."""
        try:
            last = super().last_event
        except pywikibot.exceptions.Error:
            with connect(self.site) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM `logging_userindex`
                        INNER JOIN `actor_logging`
                        ON `log_actor` = `actor_id`
                        WHERE `actor_user` = %s
                        ORDER BY `log_timestamp` DESC
                        LIMIT 1
                        """,
                        self.userid,
                    )
                    res = cursor.fetchone()
            if res is None:
                last = None
            else:
                result = {
                    k: v.decode() if isinstance(v, bytes) else v
                    for k, v in res.items()
                }
                timestamp = Timestamp.set_timestamp(result["log_timestamp"])
                fakeapidata = {
                    "logid": result["log_id"],
                    "type": result["log_type"],
                    "action": result["log_action"],
                    "timestamp": timestamp,
                }
                last = LogEntry(fakeapidata, self.site)
        for alias in self.aliases:
            if alias.last_event is None:
                continue
            if last is None or alias.last_event.timestamp > last.timestamp:
                last = alias.last_event
        return last

    def last_notification(
        self,
        note_type: _Notification,
        /,
    ) -> _NoteData | None:
        """User's last notification of the specified type."""
        try:
            notes = self.notifications[note_type]
        except KeyError:
            return None
        if notes:
            return sorted(notes, key=lambda n: n.timestamp, reverse=True)[0]
        return None

    def minimum_edits_since(
        self,
        *,
        edits: int,
        since: datetime.datetime,
    ) -> int:
        """Minimum number of edits since time."""
        actual_edits = 0
        for alias in {self} | self.aliases:
            actual_edits += sum(
                1
                for _ in alias.site.usercontribs(
                    user=alias.username,
                    end=since,
                    total=edits,
                )
            )
            if actual_edits >= edits:
                return edits
            actual_edits += sum(
                1
                for _ in alias.deleted_contributions(
                    end=since,
                    total=edits,
                )
            )
            if actual_edits >= edits:
                return edits
        return min(actual_edits, edits)

    @cached_property
    def notifications(self) -> Mapping[_Notification, set[_NoteData]]:
        """User's notifications."""
        notifications = defaultdict(set)
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM `notifications` WHERE `note_user_id` = %s",
                self.userid,
            )
            for note in cursor.fetchall():
                dtm = Timestamp.set_timestamp(note["note_rev_timestamp"])
                notifications[_Notification(note["note_type"])].add(
                    _NoteData(id=note["note_rev_id"], timestamp=dtm)
                )
        return notifications

    def notify(self, note_type: _Notification, /) -> None:
        """Send a notification to the user."""
        if self.username in _exclusions():
            pywikibot.log(f"{note_type.name} to {self!r} skipped")
            return
        crat = "yes" if "bureaucrat" in self.groups() else ""
        notification = _notifications()[note_type.name]
        talk_page = self.getUserTalkPage()
        for _ in range(3):
            with suppress(pywikibot.exceptions.Error):
                if self.site.editpage(
                    page=talk_page,
                    summary=notification["summary"],
                    minor=False,
                    bot=False,
                    section="new",
                    text=notification["text"].format(crat=crat),
                ):
                    break
        else:
            pywikibot.error(f"Failed to send {note_type!r} to {self!r}.")
            return
        if pywikibot.config.simulate:
            return
        sql1 = """
        INSERT into `notifications`
        (`note_user_id`, `note_type`, `note_rev_id`, `note_rev_timestamp`)
        VALUES (%s, %s, %s, %s)
        """
        sql2 = """
        UPDATE `users`
        SET `user_c2_desysop_timestamp` = %s,
        `user_last_updated_timestamp` = %s
        WHERE `user_id` = %s
        """
        edit_dtm = talk_page.latest_revision.timestamp
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                sql1,
                (
                    self.userid,
                    note_type.value,
                    talk_page.latest_revision_id,
                    edit_dtm.totimestampformat(),
                ),
            )
            if note_type == _Notification.C2N1:
                cursor.execute(
                    sql2,
                    (
                        (
                            edit_dtm + relativedelta(months=3)
                        ).totimestampformat(),
                        Timestamp.utcnow().totimestampformat(),
                        self.userid,
                    ),
                )
                self.__dict__.pop("database_data", None)
            connection.commit()
        self.__dict__.pop("notifications", None)
        self.__dict__.pop("c2_notification", None)

    def _to_database_dict(self) -> dict[str, int | str | None]:
        sysop = "sysop" in self.groups()
        last_rev_id = last_rev_dtm = last_rev_ts = None
        if self.last_contrib:
            last_rev_id = self.last_contrib[0]
            last_rev_dtm = self.last_contrib[1]
            last_rev_ts = last_rev_dtm.totimestampformat()
        last_log_id = last_log_ts = None
        if (
            (last_rev_dtm is not None and last_rev_dtm < NEXT_MONTH_MINUS_12M)
            or last_rev_dtm is None
        ) and self.last_event:
            last_log_id = self.last_event.logid()
            last_log_ts = self.last_event.timestamp().totimestampformat()
        if not sysop:
            c2_desysop_ts = None
        elif (
            self.database_data
            and self.database_data.c2_desysop_timestamp
            and self.c2_edits < C2_MIN_EDITS
        ):
            c2_desysop_dtm = self.database_data.c2_desysop_timestamp
            c2_desysop_ts = c2_desysop_dtm.totimestampformat()
        else:
            c2_desysop_ts = None
        return {
            "id": self.userid,
            "name": self.username,
            "last_rev_id": last_rev_id,
            "last_rev_timestamp": last_rev_ts,
            "last_log_id": last_log_id,
            "last_log_timestamp": last_log_ts,
            "c2_editcount": self.c2_edits,
            "c2_desysop_timestamp": c2_desysop_ts,
            "c2_risk_editcount": self.c2_risk_edits,
            "sysop": sysop,
            "bot": "bot" in self.groups(),
            "bureaucrat": "bureaucrat" in self.groups(),
            "last_updated": Timestamp.utcnow().totimestampformat(),
        }

    def update_database(self) -> None:
        """Update the database with the user's current data."""
        sql = """
        INSERT INTO `users`
        (
            `user_id`,
            `user_name`,
            `user_last_rev_id`,
            `user_last_rev_timestamp`,
            `user_last_log_id`,
            `user_last_log_timestamp`,
            `user_c2_editcount`,
            `user_c2_desysop_timestamp`,
            `user_c2_risk_editcount`,
            `user_sysop`,
            `user_bot`,
            `user_bureaucrat`,
            `user_last_updated_timestamp`
        )
        VALUES
        (
            %(id)s,
            %(name)s,
            %(last_rev_id)s,
            %(last_rev_timestamp)s,
            %(last_log_id)s,
            %(last_log_timestamp)s,
            %(c2_editcount)s,
            %(c2_desysop_timestamp)s,
            %(c2_risk_editcount)s,
            %(sysop)s,
            %(bot)s,
            %(bureaucrat)s,
            %(last_updated)s
        )
        ON DUPLICATE KEY UPDATE
            `user_name` = %(name)s,
            `user_last_rev_id` = %(last_rev_id)s,
            `user_last_rev_timestamp` = %(last_rev_timestamp)s,
            `user_last_log_id` = %(last_log_id)s,
            `user_last_log_timestamp` = %(last_log_timestamp)s,
            `user_c2_editcount` = %(c2_editcount)s,
            `user_c2_desysop_timestamp` = %(c2_desysop_timestamp)s,
            `user_c2_risk_editcount` = %(c2_risk_editcount)s,
            `user_sysop` = %(sysop)s,
            `user_bot` = %(bot)s,
            `user_bureaucrat` = %(bureaucrat)s,
            `user_last_updated_timestamp` = %(last_updated)s
        """
        with connect() as connection, connection.cursor() as cursor:
            cursor.execute(sql, self._to_database_dict())
            connection.commit()
        self.__dict__.pop("database_data", None)

    @property
    def userid(self) -> int:
        """User's ID."""
        return self.getprops()["userid"]


@cache
def _aliases() -> Mapping[str, str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str  # type: ignore[assignment]  # case sensitive
    parser.read(PKG_CONFIGS)
    if "aliases" in parser:
        return parser["aliases"]
    return {}


def connect(
    site: APISite | None = None,
) -> Connection[pymysql.cursors.DictCursor]:
    """Return a database connection."""
    return pymysql.connect(
        host=_database_config(site).host,
        user=_database_config(site).user,
        password=_database_config(site).password,
        database=_database_config(site).database,
        port=_database_config(site).port,
        cursorclass=pymysql.cursors.DictCursor,
    )


@cache
def _database_config(site: APISite | None = None) -> _DatabaseConfig:
    """Return the database configuration."""
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(DB_CONFIGS)
    client = parser["client"]
    if site:
        dbname = site.dbName()
        return _DatabaseConfig(
            user=client["user"],
            password=client["password"],
            database=pywikibot.config.db_name_format.format(dbname),
            host=pywikibot.config.db_hostname_format.format(dbname),
            port=pywikibot.config.db_port,
        )
    return _DatabaseConfig(
        user=client["user"],
        password=client["password"],
        database=client["database"],
        host=client["host"],
        port=int(client.get("port", "3306")),
    )


@cache
def _exclusions() -> Container[str]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(PKG_CONFIGS)
    if "excludes" in parser:
        return parser["excludes"].values()
    return []


@cache
def _notifications() -> Mapping[str, Mapping[str, str]]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(PKG_CONFIGS)
    return {
        note_type: {
            "summary": parser[note_type]["summary"],
            "text": parser[note_type]["text"],
        }
        for note_type in _Notification._member_names_
    }


def notify_c1n1(site: APISite) -> None:
    """Notify users meeting C1."""
    sql = """
    SELECT `user_name`
    FROM `users`
    WHERE `user_sysop` = TRUE
    AND `user_bot` = FALSE
    AND (
        `user_last_rev_timestamp` is NULL
        OR `user_last_rev_timestamp` < %(cutoff)s
    )
    AND (
        `user_last_log_timestamp` is NULL
        OR `user_last_log_timestamp` < %(cutoff)s
    )
    AND NOT EXISTS (
        SELECT 1
        FROM `notifications`
        WHERE `users`.`user_id` = `notifications`.`note_user_id`
        AND `note_type` IN (%(c1n1)s, %(c1n2)s)
        AND `note_rev_timestamp` >= %(last_month)s
    )
    """
    sql_dct = {
        "c1n1": _Notification.C1N1.value,
        "c1n2": _Notification.C1N2.value,
        "cutoff": NEXT_MONTH_MINUS_12M.totimestampformat(),
        "last_month": LAST_MONTH.totimestampformat(),
    }
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, sql_dct)
        result = cursor.fetchall()
    for dct in result:
        User(site, dct["user_name"]).notify(_Notification.C1N1)


def notify_c1n2(site: APISite) -> None:
    """Notify users meeting C1."""
    sql = """
    SELECT `user_name`
    FROM `users`
    LEFT JOIN `notifications`
    ON `users`.`user_id` = `notifications`.`note_user_id`
    WHERE `user_sysop` = TRUE
    AND `user_bot` = FALSE
    AND (
        `user_last_rev_timestamp` is NULL
        OR `user_last_rev_timestamp` < %(cutoff)s
    )
    AND (
        `user_last_log_timestamp` is NULL
        OR `user_last_log_timestamp` < %(cutoff)s
    )
    AND `note_type` = %(c1n1)s
    AND %(this_month)s < `note_rev_timestamp`
    """
    sql_dct = {
        "c1n1": _Notification.C1N1.value,
        "cutoff": NEXT_MONTH_MINUS_12M.totimestampformat(),
        "this_month": THIS_MONTH.totimestampformat(),
    }
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, sql_dct)
        result = cursor.fetchall()
    for dct in result:
        User(site, dct["user_name"]).notify(_Notification.C1N2)


def notify_c2(site: APISite) -> None:
    """Notify users meeting C2."""
    sql = """
    SELECT `user_name`
    FROM `users`
    WHERE `user_sysop` = TRUE
    AND `user_bot` = FALSE
    AND `user_c2_editcount` < %(c2_min_edits)s
    """
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, {"c2_min_edits": C2_MIN_EDITS})
        result = cursor.fetchall()
    for dct in result:
        user = User(site, dct["user_name"])
        if user.c2_notification:
            user.notify(user.c2_notification)


def notify_c2r(site: APISite) -> None:
    """Notify users at risk of meeting C2 anually."""
    sql = """
    SELECT `user_name`
    FROM `users`
    WHERE `user_sysop` = TRUE
    AND `user_bot` = FALSE
    AND `user_c2_risk_editcount` < %(c2_risk_edits)s
    AND NOT EXISTS (
        SELECT 1
        FROM `notifications`
        WHERE `users`.`user_id` = `notifications`.`note_user_id`
        AND `note_type` IN (%(c2n1)s, %(c2n2)s, %(c2r)s)
        AND `note_rev_timestamp` >= %(this_year)s
    )
    """
    sql_dct = {
        "c2n1": _Notification.C2N1.value,
        "c2n2": _Notification.C2N2.value,
        "c2r": _Notification.C2R.value,
        "c2_risk_edits": C2_RISK_EDITS,
        "this_year": (NOW + relativedelta(years=-1)).totimestampformat(),
    }
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, sql_dct)
        result = cursor.fetchall()
    for dct in result:
        User(site, dct["user_name"]).notify(_Notification.C2R)


def _c1_table(site: APISite) -> str:
    sql = """
    SELECT DISTINCT `user_name`
    FROM `users`
    LEFT JOIN `notifications`
    ON `users`.`user_id` = `notifications`.`note_user_id`
    WHERE `user_sysop` = TRUE
    AND `user_bot` = FALSE
    AND (
        `user_last_rev_timestamp` is NULL
        OR `user_last_rev_timestamp` < %(cutoff)s
    )
    AND (
        `user_last_log_timestamp` is NULL
        OR `user_last_log_timestamp` < %(cutoff)s
    )
    AND `note_type` IN (%(c1n1)s, %(c1n2)s)
    AND `note_rev_timestamp` >= %(this_month)s
    """
    sql_dct = {
        "c1n1": _Notification.C1N1.value,
        "c1n2": _Notification.C1N2.value,
        "cutoff": NEXT_MONTH_MINUS_12M.totimestampformat(),
        "this_month": THIS_MONTH.totimestampformat(),
    }
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, sql_dct)
        result = cursor.fetchall()
    if not result:
        return ""
    text = "{{iac1top}}\n"
    for dct in result:
        user = User(site, dct["user_name"])
        tpl = mwparserfromhell.nodes.Template("iac1row")
        tpl.add("user", user.username)
        data = user.database_data
        assert data is not None
        if data.last_rev_id and data.last_rev_timestamp:
            tpl.add("last_rev_id", data.last_rev_id)
            tpl.add("last_rev_timestamp", str(data.last_rev_timestamp))
        if data.last_log_id and data.last_log_timestamp:
            tpl.add("last_log_id", data.last_log_id)
            tpl.add("last_log_timestamp", str(data.last_log_timestamp))
        c1n1 = user.last_notification(_Notification.C1N1)
        assert c1n1 is not None
        tpl.add("note1_rev_id", c1n1.id)
        tpl.add("note1_rev_timestamp", str(c1n1.timestamp))
        c1n2 = user.last_notification(_Notification.C1N2)
        if c1n2 and c1n2.timestamp > c1n1.timestamp:
            tpl.add("note2_rev_id", c1n2.id)
            tpl.add("note2_rev_timestamp", str(c1n2.timestamp))
        text += f"{tpl}\n"
    text += "|}\n"
    return text


def _c2_table(site: APISite, dtm: Timestamp) -> str:
    sql = """
    SELECT `user_name`
    FROM `users`
    WHERE `user_sysop` = TRUE
    AND `user_bot` = FALSE
    AND `user_c2_desysop_timestamp` LIKE %s
    """
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, f"{dtm:%Y%m}%")
        result = cursor.fetchall()
    if not result:
        return ""
    text = "{{iac2top}}\n"
    for dct in result:
        user = User(site, dct["user_name"])
        tpl = mwparserfromhell.nodes.Template("iac2row")
        tpl.add("user", user.username)
        assert user.database_data is not None
        tpl.add("edits", user.database_data.c2_editcount)
        c2n1 = user.last_notification(_Notification.C2N1)
        assert c2n1 is not None
        tpl.add("note1_rev_id", c2n1.id)
        tpl.add("note1_rev_timestamp", str(c2n1.timestamp))
        c2n2 = user.last_notification(_Notification.C2N2)
        if c2n2 and c2n2.timestamp > c2n1.timestamp:
            tpl.add("note2_rev_id", c2n2.id)
            tpl.add("note2_rev_timestamp", str(c2n2.timestamp))
        text += f"{tpl}\n"
    text += "|}\n"
    return text


def list_inactive(site: APISite) -> None:
    """List inactive admins at [[Wikipedia:Inactive administrators/YYYY]]."""
    dtm = NEXT_MONTH
    while dtm <= THIS_MONTH_PLUS_3M:
        c1_table = _c1_table(site) if dtm == NEXT_MONTH else ""
        text = f"{c1_table}\n{_c2_table(site, dtm)}".strip()
        if text:
            text = (
                f"{{{{hatnote|Administrators listed below may have their "
                f"permissions removed on or after {dtm.day} {dtm:%B %Y} (UTC)"
                f" after being duly notified.}}}}\n{text}"
            )
        elif dtm > NEXT_MONTH:
            text = "Criterion 2: None"
        else:
            text = "None"
        section_date = f"{dtm:%B %Y}"
        text = f"=== {section_date} ===\n{text}\n"
        page = Page(site, f"Wikipedia:Inactive administrators/{dtm:%Y}")
        if match := page.BOT_START_END.search(page.text):
            page_text = match.group(2)
        else:
            page_text = page.text
        wikicode = mwparserfromhell.parse(page_text, skip_style_tags=True)
        for section in wikicode.get_sections(
            levels=[3],
            flat=True,
            include_lead=False,
        ):
            heading_title = section.filter_headings()[0].title.strip()
            if heading_title == section_date:
                wikicode.replace(section, f"{text}\n")
                break
        else:
            wikicode.insert(0, text)
        page.save_bot_start_end(
            str(wikicode),
            summary=f"/* {section_date} */ updating inactive admins",
            force=True,
        )
        dtm += relativedelta(months=1)


def update_admin_stats_all(site: APISite) -> None:
    """Update stats for all admins."""
    for user_dict in site.allusers(group="sysop"):
        User(site, user_dict["name"]).update_database()
    sql = """
    UPDATE `users`
    SET `user_sysop` = FALSE, `user_c2_desysop_timestamp` = NULL
    WHERE `user_sysop` = TRUE
    AND `user_last_updated_timestamp` < %s
    """
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(sql, NOW.totimestampformat())
        connection.commit()


def update_admin_stats_recent(site: APISite) -> None:
    """Update stats for recently notified admins."""
    sql = """
    SELECT `user_id`
    FROM `users`
    LEFT JOIN `notifications`
    ON `users`.`user_id` = `notifications`.`note_user_id`
    WHERE `user_sysop` = TRUE
    AND `note_rev_timestamp` >= %s
    """
    with connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            sql,
            (THIS_MONTH + relativedelta(months=-4)).totimestampformat(),
        )
        user_ids = [d["user_id"] for d in cursor.fetchall()]
    limit = 500 if site.has_right("apihighlimits") else 50
    for i in range(0, len(user_ids), limit):
        response = site.simple_request(
            action="query",
            list="users",
            ususerids=user_ids[i : i + limit],  # noqa: E203
        ).submit()
        for user_dict in response["query"]["users"]:
            User(site, user_dict["name"]).update_database()


def main(*args: str) -> int:
    """Parse arguments and run."""
    local_args = pywikibot.handle_args(args)
    site = pywikibot.Site()
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog=re.sub(
            r"\n\n?-help +.+?(\n\n-|\s*$)",
            r"\1",
            _GLOBAL_HELP,
            flags=re.S,
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "--update-recent",
        action="store_true",
        help="only update recently notified users",
    )
    parser.add_argument(
        "--notify",
        action="append",
        choices=["c1n1", "c1n2", "c2", "c2r"],
        help="notification types to send",
    )
    parsed_args = parser.parse_args(args=local_args)
    site.login()
    if parsed_args.update_recent:
        update_admin_stats_recent(site)
    else:
        update_admin_stats_all(site)
    for note_type in sorted(parsed_args.notify or []):
        globals()[f"notify_{note_type}"](site)
    list_inactive(site)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
