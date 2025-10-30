from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from datetime import datetime, timedelta
import pytz
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.bots.states import AddTask, EditTask
from app.db.session import get_conn
from app.db.repo import TaskRepo, UserRepo
from app.bots.keyboards import edit_menu_keyboard, confirm_delete_keyboard
from app.integration.icloud import ICloudClient, icloud_supported
from app.utils.timeparse import parse_user_datetime
from app.bots.scheduler import schedule_reminder, cancel_reminder
from app.integration.ics import build_ics
from app.config import settings

router = Router()


# ========== Create ==========
@router.message(F.text == "➕ Добавить задачу")
async def add_task_entry(message: Message, state: FSMContext):
    await state.set_state(AddTask.waiting_title)
    await message.answer("Введи название задачи (коротко):")


@router.message(AddTask.waiting_title)
async def add_task_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddTask.waiting_datetime)
    await message.answer("Когда начать? Например: 2025-10-28 09:30, завтра 10:00, 28.10 14:15, через 2 часа")


@router.message(AddTask.waiting_datetime)
async def add_task_datetime(message: Message, state: FSMContext):
    async with get_conn() as db:
        user = await UserRepo(db).get(message.from_user.id)
    user_tz = user.tz if user else settings.default_tz

    dt_utc = parse_user_datetime(message.text, user_tz)
    if not dt_utc:
        await message.answer("Не понял дату/время. Попробуй формат YYYY-MM-DD HH:MM или 'завтра 10:00'.")
        return

    await state.update_data(start_utc=dt_utc.isoformat(), tz=user_tz)
    await state.set_state(AddTask.waiting_duration)
    await message.answer("Длительность в минутах? (например 30, 60, 90)")


@router.message(AddTask.waiting_duration)
async def add_task_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введи целое число минут, например 30.")
        return

    await state.update_data(duration_min=duration)
    await state.set_state(AddTask.waiting_reminder)
    await message.answer("За сколько минут напомнить? (например 5, 15, 30, 60)")


@router.message(AddTask.waiting_reminder)
async def add_task_reminder(message: Message, state: FSMContext, bot):

    try:
        remind = int(message.text)
        if remind < 0:
            raise ValueError
    except Exception:
        await message.answer("Введи число минут (0 — без напоминания).")
        return

    # 2) Достаём промежуточные данные
    data = await state.get_data()
    title: str = data["title"]
    start_utc: datetime = datetime.fromisoformat(data["start_utc"])
    duration: int = data["duration_min"]
    tz: str = data["tz"]

    # 3) Пишем задачу в БД
    async with get_conn() as db:
        task_repo = TaskRepo(db)
        task_id = await task_repo.add(
            user_id=message.from_user.id,
            title=title,
            start_utc=start_utc,
            duration_min=duration,
            remind_before_min=remind,
            tz=tz,
        )

    # 4) Планируем локальное напоминание
    if remind > 0:
        start_local = start_utc.astimezone(pytz.timezone(tz))
        remind_at_local = start_local - timedelta(minutes=remind)
        await schedule_reminder(
            bot=bot,
            chat_id=message.chat.id,
            task_id=task_id,
            when=remind_at_local,
            title=title,
        )

    # 5) (опц.) Создаём событие в iCloud
    if settings.icloud_available and icloud_supported():
        try:
            start_local = start_utc.astimezone(pytz.timezone(tz))
            end_local = start_local + timedelta(minutes=duration)
            client = ICloudClient(
                settings.icloud_user,
                settings.icloud_app_password,
                settings.icloud_calendar_name,
            )
            await client.connect()
            href, uid = await client.create_event(title, start_local, end_local, tz, alarm_minutes=remind)

            async with get_conn() as db:
                if href:
                    await TaskRepo(db).set_icloud_href(task_id, href)  # если у тебя уже был такой метод
                if uid:
                    await TaskRepo(db).set_icloud_uid(task_id, uid)


            await message.answer("☁️ Добавлено в iCloud-календарь ✅")
        except Exception as e:
            await message.answer(f"⚠️ iCloud ошибка: {type(e).__name__}: {e}")

    # 6) Ответ
    await state.clear()
    local_disp = start_utc.astimezone(pytz.timezone(tz)).strftime('%Y-%m-%d %H:%M')
    await message.answer(
        f"Готово! ✅\n"
        f"Задача: {title}\n"
        f"Начало: {local_disp} ({tz})\n"
        f"Длительность: {duration} мин\n"
        f"Напоминание: за {remind} мин"
    )


# ========== List ==========
@router.message(F.text == "📋 Мои задачи")
async def list_tasks(message: Message):
    async with get_conn() as db:
        rows = await TaskRepo(db).list_upcoming(message.from_user.id)
    if not rows:
        await message.answer("Пока нет задач. Нажми ➕ Добавить задачу")
        return

    for r in rows:
        tid, title, s_utc, dur, rem, tz, href = r
        dt_local = datetime.fromisoformat(s_utc).astimezone(pytz.timezone(tz)).strftime('%Y-%m-%d %H:%M')
        link = f"\n iCloud: {href}" if href else ""
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"task:edit:{tid}"),
            InlineKeyboardButton(text="🗑 Удалить", callback_data=f"task:del:{tid}")
        ]])
        await message.answer(f"#{tid} • {title}\n{dt_local} ({tz}), {dur} мин, напоминание за {rem} мин{link}", reply_markup=kb)


# ========== Edit ==========
@router.callback_query(F.data.startswith("task:edit:"))
async def cb_task_edit(cb: CallbackQuery, state: FSMContext):
    task_id = int(cb.data.split(":")[-1])
    await state.update_data(edit_task_id=task_id)
    await cb.message.edit_text(f"Редактирование задачи #{task_id}: выбери поле", reply_markup=edit_menu_keyboard(task_id))
    await state.set_state(EditTask.choosing_field)
    await cb.answer()


@router.callback_query(F.data.startswith("edit:title:"))
async def cb_edit_title(cb: CallbackQuery, state: FSMContext):
    task_id = int(cb.data.split(":")[-1])
    await state.update_data(edit_task_id=task_id)
    await cb.message.edit_text("Введи новое название:")
    await state.set_state(EditTask.edit_title)
    await cb.answer()


@router.message(EditTask.edit_title)
async def do_edit_title(message: Message, state: FSMContext):
    data = await state.get_data()
    task_id = data["edit_task_id"]
    new_title = message.text.strip()
    async with get_conn() as db:
        await TaskRepo(db).update_title(task_id, message.from_user.id, new_title)
    await state.clear()
    await message.answer("Название обновлено ✅")


@router.callback_query(F.data.startswith("edit:dt:"))
async def cb_edit_dt(cb: CallbackQuery, state: FSMContext):
    task_id = int(cb.data.split(":")[-1])
    await state.update_data(edit_task_id=task_id)
    await cb.message.edit_text("Введи новую дату/время (например: 2025-10-28 10:00 или 'завтра 11:00'):")
    await state.set_state(EditTask.edit_datetime)
    await cb.answer()


@router.message(EditTask.edit_datetime)
async def do_edit_dt(message: Message, state: FSMContext, bot):
    data = await state.get_data()
    task_id = data["edit_task_id"]

    async with get_conn() as db:
        user = await UserRepo(db).get(message.from_user.id)
    user_tz = user.tz if user else settings.default_tz

    dt_utc = parse_user_datetime(message.text, user_tz)
    if not dt_utc:
        await message.answer("Не понял дату/время. Попробуй снова.")
        return

    async with get_conn() as db:
        row = await TaskRepo(db).get_core(task_id, message.from_user.id)
    if not row:
        await message.answer("Задача не найдена.")
        await state.clear()
        return

    title, remind, tz, duration = row

    async with get_conn() as db:
        await TaskRepo(db).update_start(task_id, message.from_user.id, dt_utc)

    async with get_conn() as db:
        row_uid = await TaskRepo(db).get_uid_tz_dur(task_id, message.from_user.id)

    if row_uid and row_uid[0]:
        ic_uid, tz, duration = row_uid
        try:
            start_local = dt_utc.astimezone(pytz.timezone(tz))
            end_local = start_local + timedelta(minutes=duration)
            from app.integration.icloud import ICloudClient
            client = ICloudClient(
                settings.icloud_user,
                settings.icloud_app_password,
                settings.icloud_calendar_name
            )
            await client.connect()
            await client.update_event_by_uid(ic_uid, title, start_local, end_local, tz, alarm_minutes=remind)
        except Exception as e:
            print(f"[iCloud] Не удалось обновить событие: {e}")

    if remind and remind > 0:
        start_local = dt_utc.astimezone(pytz.timezone(tz))
        remind_at_local = start_local - timedelta(minutes=remind)
        cancel_reminder(task_id)
        await schedule_reminder(bot, message.chat.id, task_id, remind_at_local, title)

    await state.clear()
    await message.answer("Дата/время обновлены ✅")


@router.callback_query(F.data.startswith("edit:dur:"))
async def cb_edit_dur(cb: CallbackQuery, state: FSMContext):
    task_id = int(cb.data.split(":")[-1])
    await state.update_data(edit_task_id=task_id)
    await cb.message.edit_text("Новое значение длительности (мин):")
    await state.set_state(EditTask.edit_duration)
    await cb.answer()


@router.message(EditTask.edit_duration)
async def do_edit_dur(message: Message, state: FSMContext):
    try:
        new_dur = int(message.text)
        if new_dur <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введи целое число минут > 0")
        return

    data = await state.get_data()
    task_id = data["edit_task_id"]
    async with get_conn() as db:
        await TaskRepo(db).update_duration(task_id, message.from_user.id, new_dur)

    await state.clear()
    await message.answer("Длительность обновлена ✅")


@router.callback_query(F.data.startswith("edit:rem:"))
async def cb_edit_rem(cb: CallbackQuery, state: FSMContext):
    task_id = int(cb.data.split(":")[-1])
    await state.update_data(edit_task_id=task_id)
    await cb.message.edit_text("За сколько минут напоминать? (0 — отключить)")
    await state.set_state(EditTask.edit_reminder)
    await cb.answer()


@router.message(EditTask.edit_reminder)
async def do_edit_rem(message: Message, state: FSMContext, bot):
    try:
        new_rem = int(message.text)
        if new_rem < 0:
            raise ValueError
    except Exception:
        await message.answer("Введи число минут (0 — без напоминания)")
        return

    data = await state.get_data()
    task_id = data["edit_task_id"]

    async with get_conn() as db:
        row = await TaskRepo(db).get_start_title_tz(task_id, message.from_user.id)
    if not row:
        await message.answer("Задача не найдена.")
        await state.clear()
        return

    start_utc_s, title, tz = row

    async with get_conn() as db:
        await TaskRepo(db).update_reminder(task_id, message.from_user.id, new_rem)
        # обновляем VALARM в iCloud
        async with get_conn() as db:
            row2 = await TaskRepo(db).get_uid_tz_dur(task_id, message.from_user.id)
        if row2 and row2[0]:
            ic_uid, tz, duration = row2
            start_utc = datetime.fromisoformat(start_utc_s)
            start_local = start_utc.astimezone(pytz.timezone(tz))
            end_local = start_local + timedelta(minutes=duration)
            try:
                from app.integration.icloud import ICloudClient
                client = ICloudClient(settings.icloud_user, settings.icloud_app_password, settings.icloud_calendar_name)
                await client.connect()
                await client.update_event_by_uid(ic_uid, title, start_local, end_local, tz, alarm_minutes=new_rem)
            except Exception:
                pass

    # Перепланируем/отключим напоминание
    cancel_reminder(task_id)
    if new_rem > 0:
        start_utc = datetime.fromisoformat(start_utc_s)
        start_local = start_utc.astimezone(pytz.timezone(tz))
        remind_at_local = start_local - timedelta(minutes=new_rem)
        await schedule_reminder(bot, message.chat.id, task_id, remind_at_local, title)

    await state.clear()
    await message.answer("Напоминание обновлено ✅")


# ========== Delete ==========
@router.callback_query(F.data.startswith("task:del:"))
async def cb_task_del(cb: CallbackQuery):
    task_id = int(cb.data.split(":")[-1])
    await cb.message.edit_text(f"Удалить задачу #{task_id}?", reply_markup=confirm_delete_keyboard(task_id))
    await cb.answer()


@router.callback_query(F.data.startswith("del:"))
async def do_delete(cb: CallbackQuery):
    parts = cb.data.split(":")
    vote, task_id = parts[1], int(parts[2])

    if vote == "no":
        await cb.message.edit_text("Удаление отменено.")
        await cb.answer()
        return

    async with get_conn() as db:
        await TaskRepo(db).delete(task_id, cb.from_user.id)

    cancel_reminder(task_id)
    await cb.message.edit_text("Задача удалена ✅")
    await cb.answer()


# ========== Export ICS ==========
@router.message(F.text == "📤 Экспорт в iOS (.ics)")
async def export_ics(message: Message):
    limit = getattr(settings, "export_limit", 50)
    async with get_conn() as db:
        cur = await db.execute(
            "SELECT title, start_utc, duration_min, tz "
            "FROM tasks WHERE user_id=? ORDER BY start_utc ASC LIMIT ?",
            (message.from_user.id, limit)
        )
        tasks = await cur.fetchall()

    if not tasks:
        await message.answer("Нет задач для экспорта.")
        return

    filename = f"tasks_{message.from_user.id}.ics"
    path = build_ics(tasks, filename)
    await message.answer_document(FSInputFile(path), caption="Импортируй файл в Календарь на iPhone.")

@router.callback_query(F.data.startswith("rem:ack:"))
async def cb_rem_ack(cb: CallbackQuery):
    try:
        task_id = int(cb.data.split(":")[2])
    except Exception:
        await cb.answer("Некорректный идентификатор.", show_alert=True)
        return

    cancel_reminder(task_id)  # гасим активное напоминание (job id один и тот же)
    await cb.answer("Напоминание отключено ✅", show_alert=True)
    # опционально: обновим текст сообщения
    try:
        if cb.message:
            await cb.message.edit_text((cb.message.text or "") + "\n\n✅ Отмечено как выполнено")
    except Exception:
        pass

# ⏰ Отложить: "Через N минут"
@router.callback_query(F.data.startswith("rem:snooze:"))
async def cb_rem_snooze(cb: CallbackQuery, bot):
    parts = cb.data.split(":")
    if len(parts) != 4:
        await cb.answer("Ошибка параметров.", show_alert=True)
        return
    _, _, task_id_s, minutes_s = parts
    try:
        task_id = int(task_id_s)
        minutes = int(minutes_s)
    except Exception:
        await cb.answer("Ошибка параметров.", show_alert=True)
        return

    # достанем заголовок и tz пользователя для корректного локального now
    async with get_conn() as db:
        row = await TaskRepo(db).get_start_title_tz(task_id, cb.from_user.id)
    if not row:
        await cb.answer("Задача не найдена.", show_alert=True)
        return

    start_utc_s, title, tz = row
    now_local = datetime.now(tz=pytz.timezone(tz))
    when_local = now_local + timedelta(minutes=minutes)

    # перепланируем ТУ ЖЕ задачу (replace_existing=True в schedule_reminder)
    await schedule_reminder(
        bot=bot,
        chat_id=cb.message.chat.id,
        task_id=task_id,
        when=when_local,
        title=title,
    )
    await cb.answer(f"Ок, напомню через {minutes} мин ⏰", show_alert=True)

    # опционально: визуально отметим отложение
    try:
        if cb.message:
            await cb.message.edit_text((cb.message.text or "") + f"\n⏰ Отложено на {minutes} мин")
    except Exception:
        pass