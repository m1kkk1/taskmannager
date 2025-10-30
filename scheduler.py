from __future__ import annotations
from datetime import datetime
from apscheduler.triggers.date import DateTrigger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


_SCHED: AsyncIOScheduler | None = None

def create_scheduler(timezone: str) -> AsyncIOScheduler:
    global _SCHED
    _SCHED = AsyncIOScheduler(timezone=timezone)
    _SCHED.start()
    return _SCHED

def get_scheduler() -> AsyncIOScheduler:
    if _SCHED is None:
        raise RuntimeError("Scheduler is not initialized yet")
    return _SCHED

def cancel_reminder(task_id: int):
    sched = get_scheduler()
    job_id = f"reminder_{task_id}"
    try:
        sched.remove_job(job_id)
    except Exception:
        pass

async def schedule_reminder(*, bot, chat_id: int, task_id: int, when: datetime, title: str):
    """
    Планирует одиночное напоминание для задачи.
    ВАЖНО: id фиксированный (reminder_{task_id}) + replace_existing=True ⇒ дубликатов не будет.
    """
    # импортируем внутри, чтобы избежать циклических импортов


    async def send():
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Готово", callback_data=f"rem:ack:{task_id}"),
            InlineKeyboardButton(text="⏰ Через 5 мин", callback_data=f"rem:snooze:{task_id}:5"),
            InlineKeyboardButton(text="🕐 Через 15 мин", callback_data=f"rem:snooze:{task_id}:15"),
        ]])
        # disable_notification=False гарантирует пуш (если чат не заглушен пользователем)
        text = f"🔔 Напоминание\n«{title}»"
        await bot.send_message(chat_id, text, reply_markup=kb, disable_notification=False)

    get_scheduler().add_job(
        send,
        trigger=DateTrigger(run_date=when),
        id=f"reminder_{task_id}",
        replace_existing=True,   # ← ключ: не плодим новые jobs
        misfire_grace_time=120,
    )
