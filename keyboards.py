from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить задачу"), KeyboardButton(text="📋 Мои задачи")],
            [KeyboardButton(text="📤 Экспорт в iOS (.ics)"), KeyboardButton(text="⏰ Уведомления")],
            [KeyboardButton(text="🗓 iCloud статус"), KeyboardButton(text="🌍 Часовой пояс")],
        ], resize_keyboard=True
    )

def notify_keyboard(default_min: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 мин", callback_data="rem:5"),
         InlineKeyboardButton(text="15 мин", callback_data="rem:15"),
         InlineKeyboardButton(text="30 мин", callback_data="rem:30")],
        [InlineKeyboardButton(text="1 час", callback_data="rem:60"),
         InlineKeyboardButton(text="2 часа", callback_data="rem:120")],
        [InlineKeyboardButton(text=f"Текущая: {default_min} мин — оставить", callback_data=f"rem:{default_min}")]
    ])

def edit_menu_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Название", callback_data=f"edit:title:{task_id}")],
        [InlineKeyboardButton(text="Дата/время", callback_data=f"edit:dt:{task_id}")],
        [InlineKeyboardButton(text="Длительность", callback_data=f"edit:dur:{task_id}")],
        [InlineKeyboardButton(text="Напоминание", callback_data=f"edit:rem:{task_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"edit:back:{task_id}")]
    ])

def confirm_delete_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да, удалить", callback_data=f"del:yes:{task_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"del:no:{task_id}")]
    ])
