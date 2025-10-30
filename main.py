# app/main.py
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db.session import init_db
from app.bots.scheduler import create_scheduler
from app.bots.handlers import start as start_handlers
from app.bots.handlers import tasks as tasks_handlers
from app.bots.handlers import settings as settings_handlers

# Логирование по уровню из конфига
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("taskplanner")

# Глобальный планировщик (нужен внутри handlers)
scheduler = None


async def main():
    global scheduler

    if not settings.bot_token:
        logger.error("BOT_TOKEN пуст — добавь его в app/config.py (settings.bot_token)")
        return

    # 1) Инициализация БД (создастся из schema.sql)
    await init_db()

    # 2) Бот, Диспетчер, Планировщик
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    scheduler_tz = settings.scheduler_timezone or settings.default_tz
    scheduler = create_scheduler(timezone=scheduler_tz)

    # 3) Проверка токена
    try:
        me = await bot.get_me()
        logger.info(f"Авторизован как @{me.username} ({me.id})")
    except Exception:
        logger.exception("Не удалось авторизоваться: проверь settings.bot_token в app/config.py")
        await bot.session.close()
        return

    # 4) Роутеры
    dp.include_router(start_handlers.router)
    dp.include_router(tasks_handlers.router)
    dp.include_router(settings_handlers.router)

    # 5) Старт
    logger.info("Bot started")
    try:
        await dp.start_polling(bot)
    finally:
        # Аккуратно закрываем HTTP-сессию бота
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by keyboard")
