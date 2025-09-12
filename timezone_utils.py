from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date, time, timezone
from typing import Optional

from timezonefinder import TimezoneFinder
from zoneinfo import ZoneInfo


tf = TimezoneFinder()


@dataclass
class TimezoneResolution:
    tzid: str
    offset_minutes: int
    birth_datetime_utc: datetime


def resolve_timezone(lat: float, lon: float, local_date: date, local_time: time) -> Optional[TimezoneResolution]:
    """Определяет часовой пояс и UTC-смещение для заданных координат и локального времени.

    Возвращает TimezoneResolution, либо None если определить не удалось.
    """
    try:
        tzid = tf.timezone_at(lat=lat, lng=lon)
    except Exception:
        tzid = None
    if not tzid:
        return None

    try:
        tz = ZoneInfo(tzid)
    except Exception:
        return None

    # Локальное время рождения с TZ
    local_dt = datetime.combine(local_date, local_time, tzinfo=tz)
    # Смещение от UTC в минутах
    offset = local_dt.utcoffset() or timezone.utc.utcoffset(local_dt)
    if offset is None:
        return None
    offset_minutes = int(offset.total_seconds() // 60)
    # Перевод в UTC
    dt_utc = local_dt.astimezone(timezone.utc)

    return TimezoneResolution(tzid=tzid, offset_minutes=offset_minutes, birth_datetime_utc=dt_utc)


def format_utc_offset(minutes: int) -> str:
    sign = '+' if minutes >= 0 else '-'
    m = abs(minutes)
    hh = m // 60
    mm = m % 60
    return f"UTC{sign}{hh:02d}:{mm:02d}"
