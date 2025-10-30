from aiogram.fsm.state import StatesGroup, State

class AddTask(StatesGroup):
    waiting_title = State()
    waiting_datetime = State()
    waiting_duration = State()
    waiting_reminder = State()

class EditTask(StatesGroup):
    choosing_field = State()
    edit_title = State()
    edit_datetime = State()
    edit_duration = State()
    edit_reminder = State()
