# reminder - A maubot plugin to remind you about things.
# Copyright (C) 2020 Tulir Asokan
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
from typing import Optional, Dict, List, Union, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta
from attr import dataclass
import re

import pytz
from dateutil.relativedelta import relativedelta

from mautrix.types import UserID, RoomID, EventID
from mautrix.util.config import BaseProxyConfig, ConfigUpdateHelper
from maubot import MessageEvent
from maubot.handlers.command import Argument, ArgumentSyntaxError

if TYPE_CHECKING:
    from .bot import ReminderBot


class Config(BaseProxyConfig):
    def do_update(self, helper: ConfigUpdateHelper) -> None:
        helper.copy("base_command")


timedelta_regex = re.compile(r"(?:(?P<years>[-+]?\d+)\s?y(?:ears?)?\s?)?"
                             r"(?:(?P<months>[-+]?\d+)\s?months?\s?)?"
                             r"(?:(?P<weeks>[-+]?\d+)\s?w(?:eeks?)?\s?)?"
                             r"(?:(?P<days>[-+]?\d+)\s?d(?:ays?)?\s?)?"
                             r"(?:(?P<hours>[-+]?\d+)\s?h(?:ours?)?\s?)?"
                             r"(?:(?P<minutes>[-+]?\d+)\s?m(?:inutes?)?\s?)?"
                             r"(?:(?P<seconds>[-+]?\d+)\s?s(?:econds?)?\s?)?",
                             flags=re.IGNORECASE)
date_regex = re.compile(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})")
day_regex = re.compile(r"today"
                       r"|tomorrow"
                       r"|mon(?:day)?"
                       r"|tues?(?:day)?"
                       r"|wed(?:nesday)?"
                       r"|thu(?:rs(?:day)?)?"
                       r"|fri(?:day)?"
                       r"|sat(?:urday)?"
                       r"|sun(?:day)?",
                       flags=re.IGNORECASE)
time_regex = re.compile(r"(?:\sat\s)?(?P<hour>\d{2})"
                        r"[:.](?P<minute>\d{2})"
                        r"(?:[:.](?P<second>\d{2}))?",
                        flags=re.IGNORECASE)


class DateArgument(Argument):
    def __init__(self, name: str, label: str = None, *, required: bool = False):
        super().__init__(name, label=label, required=required, pass_raw=True)

    def match(self, val: str, evt: MessageEvent = None, instance: 'ReminderBot' = None
              ) -> Tuple[str, Optional[datetime]]:
        tz = pytz.UTC
        if instance:
            tz = instance.db.get_timezone(evt.sender)

        found_delta = timedelta_regex.match(val)
        end = 0
        if found_delta.end() > 0:
            params = {k: float(v) for k, v in found_delta.groupdict().items() if v}
            end = found_delta.end()
        else:
            params = {}
            found_day = day_regex.match(val)
            if found_day:
                end = found_day.end()
                params["weekday"] = {
                    "tod": datetime.now().weekday(), "tom": datetime.now().weekday() + 1,
                    "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                }[found_day.string[:3].lower()]
            else:
                found_date = date_regex.match(val)
                if found_date:
                    end = found_date.end()
                    params = {k: int(v) for k, v in found_delta.groupdict().items() if v}

            found_time = time_regex.match(val, pos=end)
            if found_time:
                params = {
                    **params,
                    **{k: int(v) for k, v in found_time.groupdict().items() if v}
                }
                end = found_time.end()

        return val[end:], ((datetime.now(tz=tz) + relativedelta(**params))
                           if len(params) > 0 else None)


def parse_timezone(val: str) -> Optional[pytz.timezone]:
    if not val:
        return None
    try:
        return pytz.timezone(val)
    except pytz.UnknownTimeZoneError as e:
        raise ArgumentSyntaxError(f"{val} is not a valid time zone.", show_usage=False) from e


def pluralize(val: int, unit: str) -> str:
    if val == 1:
        return f"{val} {unit}"
    return f"{val} {unit}s"


def format_time(time: datetime) -> str:
    now = datetime.now(tz=pytz.UTC).replace(microsecond=0)
    if time - now <= timedelta(days=7):
        delta = time - now
        parts = []
        if delta.days > 0:
            parts.append(pluralize(delta.days, "day"))
        hours, seconds = divmod(delta.seconds, 60)
        hours, minutes = divmod(hours, 60)
        if hours > 0:
            parts.append(pluralize(hours, "hour"))
        if minutes > 0:
            parts.append(pluralize(minutes, "minute"))
        if seconds > 0:
            parts.append(pluralize(seconds, "second"))
        if len(parts) == 1:
            return "in " + parts[0]
        return "in " + ", ".join(parts[:-1]) + f" and {parts[-1]}"
    return time.strftime("at %H:%M:%S %Z on %A, %B %-d %Y")


@dataclass
class ReminderInfo:
    id: int = None
    date: datetime = None
    room_id: RoomID = None
    event_id: EventID = None
    message: str = None
    reply_to: EventID = None
    users: Union[Dict[UserID, EventID], List[UserID]] = None
