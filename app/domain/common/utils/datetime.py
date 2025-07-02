"""DateTime Utilities Module"""

import datetime as _dt
from typing import ClassVar
from zoneinfo import ZoneInfo

from kink import di

_DateLike = str | _dt.date | _dt.datetime


class DateTimeUtils:
    ISO_FORMATS: ClassVar = [
        '%Y-%m-%d',
        '%Y-%m-%dT%H:%M',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
    ]

    @staticmethod
    def parse(date_like: _DateLike, tz: _dt.timezone | None = None) -> _dt.datetime:
        if isinstance(date_like, _dt.datetime):
            return date_like.astimezone(tz) if tz else date_like

        if isinstance(date_like, _dt.date):
            return _dt.datetime(
                date_like.year, date_like.month, date_like.day, tzinfo=tz
            )

        for fmt in DateTimeUtils.ISO_FORMATS:
            try:
                return _dt.datetime.strptime(date_like, fmt).replace(tzinfo=tz)

            except (ValueError, TypeError):
                continue

        msg = f'unable to parse date: {date_like}'
        raise ValueError(msg)

    @staticmethod
    def now() -> _dt.datetime:
        return _dt.datetime.now(tz=di[ZoneInfo])

    @staticmethod
    def today() -> _dt.date:
        return _dt.datetime.now(tz=di[ZoneInfo]).date().today()

    @staticmethod
    def start_of_day(dt: _dt.datetime) -> _dt.datetime:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def end_of_day(dt: _dt.datetime) -> _dt.datetime:
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    @staticmethod
    def add(
        dt: _dt.datetime,
        *,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
    ) -> _dt.datetime:
        return dt + _dt.timedelta(
            days=days, hours=hours, minutes=minutes, seconds=seconds
        )

    @staticmethod
    def format(dt: _dt.datetime, fmt: str = '%Y-%m-%dT%H:%M:%S%z') -> str:
        return dt.strftime(fmt)
