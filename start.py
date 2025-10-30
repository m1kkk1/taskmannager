from datetime import timedelta, datetime

import pytz
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message

from app.config import settings as cfg
from app.db.session import get_conn
from app.db.repo import UserRepo
from app.bots.keyboards import main_menu
from app.integration.icloud import ICloudClient, icloud_supported

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    async with get_conn() as db:
        await UserRepo(db).ensure_user(message.from_user.id)
    await message.answer("Привет! Я планировщик задач. Добавляй задачи, ставь напоминания и экспортируй в календарь iPhone.",
                         reply_markup=main_menu())

@router.message(F.text == "🗓 iCloud статус")
async def icloud_status(message: Message):
    from app.config import settings
    from app.integration.icloud import icloud_supported
    s = settings()
    if s.icloud_available and icloud_supported():
        await message.answer("iCloud интеграция: доступна ✅ — события будут добавляться в выбранный календарь.")
    else:
        await message.answer("iCloud интеграция: недоступна ❌ — укажи ICLOUD_USER/ICLOUD_APP_PASSWORD или используй экспорт .ics.")

@router.message(Command("icloud_test"))
async def icloud_test(message: Message,):
    if not cfg.icloud_available:
        await message.answer("iCloud не настроен (заполни icloud_user и icloud_app_password в config.py).")
        return
    if not icloud_supported():
        await message.answer("Пакет 'caldav' не установлен. Выполни: pip install caldav")
        return
    try:
        tz = pytz.timezone(cfg.default_tz)
        start = datetime.now(tz) + timedelta(minutes=2)
        end = start + timedelta(minutes=30)
        client = ICloudClient(cfg.icloud_user, cfg.icloud_app_password, cfg.icloud_calendar_name)
        await client.connect()
        href = await client.create_event("Test from TaskPlanner", start, end, cfg.default_tz)
        await message.answer(f"iCloud тест: OK\n{href or '(без href)'}")
    except Exception as e:
        await message.answer(f"iCloud тест: ошибка — {type(e).__name__}: {e}")

@router.message(Command("icloud_calendars"))
async def icloud_calendars(message: Message):
    if not cfg.icloud_available:
        await message.answer("iCloud не настроен (заполни icloud_user и icloud_app_password в config.py).")
        return
    if not icloud_supported():
        await message.answer("Пакет 'caldav' не установлен. Выполни: pip install caldav")
        return
    try:
        client = ICloudClient(cfg.icloud_user, cfg.icloud_app_password, cfg.icloud_calendar_name)
        await client.connect()
        names = await client.list_calendars()
        if not names:
            await message.answer("Календари не найдены в iCloud.")
            return
        await message.answer("Доступные календари:\n" + "\n".join(f"• {n}" for n in names))
    except Exception as e:
        await message.answer(f"Ошибка: {type(e).__name__}: {e}")

@router.message(Command("icloud_today"))
async def icloud_today(message: Message):
    if not cfg.icloud_available:
        await message.answer("iCloud не настроен (заполни icloud_user и icloud_app_password в config.py).")
        return
    if not icloud_supported():
        await message.answer("Пакет 'caldav' не установлен. Выполни: pip install caldav")
        return
    try:
        tz = pytz.timezone(cfg.default_tz)
        start = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)

        client = ICloudClient(cfg.icloud_user, cfg.icloud_app_password, cfg.icloud_calendar_name)
        await client.connect()
        items = await client.list_events(start, end)

        if not items:
            await message.answer("Событий за сегодня в выбранном календаре не найдено.")
            return

        lines = []
        for ev in items:
            lines.append(f"• {ev['start']} — {ev['end']} | {ev['summary']} (UID: {ev['uid']})")
        await message.answer("Сегодня в iCloud:\n" + "\n".join(lines))
    except Exception as e:
        await message.answer(f"Ошибка: {type(e).__name__}: {e}")