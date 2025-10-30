from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from app.db.session import get_conn
from app.db.repo import UserRepo
from app.bots.keyboards import notify_keyboard
import pytz

router = Router()

@router.message(F.text == "⏰ Уведомления")
async def change_default_notify(message: Message):
    async with get_conn() as db:
        user = await UserRepo(db).get(message.from_user.id)
    current = user.default_remind_min if user else 15
    await message.answer("Выбери напоминание по умолчанию:", reply_markup=notify_keyboard(current))

@router.callback_query(F.data.startswith("rem:"))
async def set_default_notify(cb: CallbackQuery):
    minutes = int(cb.data.split(":")[1])
    async with get_conn() as db:
        await UserRepo(db).set_default_remind(cb.from_user.id, minutes)
    await cb.message.edit_text(f"Готово. Напоминание по умолчанию: {minutes} мин.")
    await cb.answer("Сохранено")


@router.message(F.text == "🌍 Часовой пояс")
async def change_tz(message: Message):
    await message.answer("Введи IANA таймзону (например Europe/Kyiv, Europe/Warsaw, Asia/Almaty)")

@router.message(F.text.regexp(r"^[A-Za-z]+/[A-Za-z_]+"))
async def set_tz(message: Message):
    tz_str = message.text.strip()
    if tz_str not in pytz.all_timezones:
        await message.answer("Неизвестный часовой пояс. Попробуй ещё раз.")
        return
    async with get_conn() as db:
        await UserRepo(db).set_tz(message.from_user.id, tz_str)
    await message.answer(f"Часовой пояс обновлён: {tz_str}")


