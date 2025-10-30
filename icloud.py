# app/integration/icloud.py
from __future__ import annotations

from typing import Optional, Tuple, Any
from uuid import uuid4
import logging, time
from icalendar import Calendar, Event, Alarm
from datetime import datetime, timedelta
from pytz import UTC

# --- CalDAV (может отсутствовать, тогда icloud_supported() вернёт False) ---
try:
    from caldav import DAVClient, Calendar
    from caldav.elements import dav
except Exception:
    DAVClient = None
    dav = None

# --- ICS ---
from icalendar import Calendar, Event

logger = logging.getLogger("taskplanner.icloud")


class ICloudClient:
    def __init__(self, user: str, app_password: str, calendar_name: str):
        self.user = user
        self.app_password = app_password
        self.calendar_name = calendar_name
        self._client: Optional[DAVClient] = None
        self._calendar = None

    async def connect(self):
        """Подключиться к CalDAV и найти/создать календарь по displayname."""
        if DAVClient is None:
            raise RuntimeError("Библиотека 'caldav' не установлена")

        import asyncio
        loop = asyncio.get_running_loop()

        def _connect_and_pick() -> list[DAVClient | None | Any]:
            client = DAVClient(
                url="https://caldav.icloud.com/",
                username=self.user,
                password=self.app_password,
            )
            principal = client.principal()
            calendars = principal.calendars()

            def display_name(cal) -> str:
                try:
                    props = cal.get_properties([dav.DisplayName()])
                    name = str(props.get(dav.DisplayName(), "")).strip()
                    return name
                except Exception:
                    return ""

            target = None
            for c in calendars:
                name = display_name(c)
                if name == self.calendar_name:
                    target = c
                    break

            if target is None:
                target = principal.make_calendar(name=self.calendar_name)

            return [client, target]

        self._client, self._calendar = await loop.run_in_executor(None, _connect_and_pick)
        logger.info("iCloud CalDAV connected, calendar ready: %s", self.calendar_name)

    async def create_event(
            self,
            title: str,
            start_local: datetime,
            end_local: datetime,
            tz: str,
            alarm_minutes: int | None = None,  # ⟵ НОВОЕ
    ) -> tuple[str, str]:
        if self._calendar is None:
            await self.connect()

        import asyncio, time
        loop = asyncio.get_running_loop()
        uid = str(uuid4())

        def _put_and_resolve_href() -> str:
            cal = Calendar()
            cal.add("prodid", "-//TaskPlannerBot//")
            cal.add("version", "2.0")

            ev = Event()
            ev.add("uid", uid)
            ev.add("summary", title)
            ev.add("dtstart", start_local.astimezone(UTC))
            ev.add("dtend", end_local.astimezone(UTC))
            ev.add("dtstamp", datetime.utcnow().replace(tzinfo=UTC))
            ev.add("status", "CONFIRMED")
            ev.add("transp", "OPAQUE")


            if alarm_minutes and alarm_minutes > 0:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"Reminder: {title}")
                alarm.add("trigger", timedelta(minutes=-alarm_minutes))  # за N мин до начала
                ev.add_component(alarm)

            cal.add_component(ev)
            ics_bytes = cal.to_ical()

            href = ""
            try:
                href_raw = self._calendar.save_event(ics_bytes)
                href = str(href_raw) if href_raw else ""
            except Exception as e:
                logger.warning("save_event() returned no href: %s", e)

            if href:
                return href

            # короткие ретраи на случай задержки индексации
            for attempt in range(3):
                try:
                    window_start = start_local - timedelta(days=1)
                    window_end = end_local + timedelta(days=1)
                    found = self._calendar.date_search(window_start, window_end)
                    for ev_obj in found:
                        try:
                            raw = ev_obj.data
                            if not raw:
                                continue
                            parsed = Calendar.from_ical(raw)
                            for comp in parsed.walk():
                                if comp.name == "VEVENT" and str(comp.get("uid", "")).strip() == uid:
                                    url = getattr(ev_obj, "url", None) or getattr(ev_obj, "id", None)
                                    if url:
                                        return str(url)
                        except Exception:
                            continue
                except Exception as e:
                    logger.warning("date_search() failed on attempt %s: %s", attempt + 1, e)
                time.sleep(1.0)
            return ""

        href = await loop.run_in_executor(None, _put_and_resolve_href)
        if href:
            logger.info("iCloud event created: %s → %s", title, href)
        else:
            logger.info("iCloud event created without href: %s", title)
        return href, uid

    async def _find_event_by_uid(self, uid: str, start_local: datetime, end_local: datetime):
        """Ищем событие по UID в окне дат (±1 день). Возвращаем caldav Event или None."""
        if self._calendar is None:
            await self.connect()

        import asyncio
        loop = asyncio.get_running_loop()

        def _search():
            window_start = start_local - timedelta(days=1)
            window_end = end_local + timedelta(days=1)
            found = self._calendar.date_search(window_start, window_end)
            for ev_obj in found:
                try:
                    raw = ev_obj.data
                    if not raw:
                        continue
                    parsed = Calendar.from_ical(raw)
                    for comp in parsed.walk():
                        if comp.name == "VEVENT":
                            parsed_uid = str(comp.get("uid", "")).strip()
                            if parsed_uid == uid:
                                return ev_obj
                except Exception:
                    continue
            return None

        return await loop.run_in_executor(None, _search)

    async def update_event_by_uid(
            self,
            uid: str,
            title: str,
            start_local: datetime,
            end_local: datetime,
            tz: str,
            alarm_minutes: int | None = None,  # ⟵ НОВОЕ
    ) -> bool:
        ev_obj = await self._find_event_by_uid(uid, start_local, end_local)
        if ev_obj is None:
            return False

        import asyncio
        loop = asyncio.get_running_loop()

        def _update():
            cal = Calendar()
            cal.add("prodid", "-//TaskPlannerBot//")
            cal.add("version", "2.0")

            ev = Event()
            ev.add("uid", uid)
            ev.add("summary", title)
            ev.add("dtstart", start_local.astimezone(UTC))
            ev.add("dtend", end_local.astimezone(UTC))
            ev.add("dtstamp", datetime.utcnow().replace(tzinfo=UTC))
            ev.add("status", "CONFIRMED")
            ev.add("transp", "OPAQUE")


            if alarm_minutes and alarm_minutes > 0:
                alarm = Alarm()
                alarm.add("action", "DISPLAY")
                alarm.add("description", f"Reminder: {title}")
                alarm.add("trigger", timedelta(minutes=-alarm_minutes))
                ev.add_component(alarm)

            cal.add_component(ev)
            ev_obj.data = cal.to_ical()
            ev_obj.save()
            return True

        return await loop.run_in_executor(None, _update)

    async def delete_event_by_uid(self, uid: str, start_local: datetime, end_local: datetime) -> bool:
        """Удаляем событие по UID (ищем в окне дат)."""
        ev_obj = await self._find_event_by_uid(uid, start_local, end_local)
        if ev_obj is None:
            return False

        import asyncio
        loop = asyncio.get_running_loop()

        def _delete():
            ev_obj.delete()
            return True

        return await loop.run_in_executor(None, _delete)

    # ===== Диагностика / сервис =====

    async def list_calendars(self):
        """Список displayName календарей в iCloud (для диагностики)."""
        if self._client is None or self._calendar is None:
            await self.connect()
        import asyncio
        loop = asyncio.get_running_loop()

        def _list():
            principal = self._client.principal()
            calendars = principal.calendars()
            out = []
            for c in calendars:
                try:
                    props = c.get_properties([dav.DisplayName()])
                    name = str(props.get(dav.DisplayName(), "")).strip()
                except Exception:
                    name = "(no displayname)"
                out.append(name)
            return out

        return await loop.run_in_executor(None, _list)

    async def list_events(self, start_local: datetime, end_local: datetime):
        """Вернёт список событий (summary, start, end, uid) за период."""
        if self._calendar is None:
            await self.connect()
        import asyncio
        loop = asyncio.get_running_loop()

        def _fetch():
            out = []
            found = self._calendar.date_search(start_local, end_local)
            for ev_obj in found:
                try:
                    raw = ev_obj.data
                    if not raw:
                        continue
                    cal = Calendar.from_ical(raw)
                    for comp in cal.walk():
                        if comp.name != "VEVENT":
                            continue
                        summ = str(comp.get("summary", "")).strip()
                        uid = str(comp.get("uid", "")).strip()
                        dtstart = comp.get("dtstart").dt
                        dtend = comp.get("dtend").dt
                        out.append({"summary": summ, "uid": uid, "start": dtstart, "end": dtend})
                except Exception:
                    continue
            return out

        return await loop.run_in_executor(None, _fetch)


def icloud_supported() -> bool:
    """Доступна ли интеграция (есть caldav)?"""
    return DAVClient is not None and dav is not None
