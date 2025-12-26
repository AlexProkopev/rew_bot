# telegram_reviews_bot/bot.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
import database as db
from handlers import start, reviews, admin, show_reviews

async def main():
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    
    # Инициализация базы данных
    await db.init_db()

    # Инициализация бота и диспетчера
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(reviews.router)
    dp.include_router(show_reviews.router)
    dp.include_router(admin.router) # Админский роутер должен быть последним, чтобы его фильтры не мешали другим

    try:
        # Удаление вебхука и запуск поллинга
        try:
            await bot.delete_webhook(drop_pending_updates=True, request_timeout=60)
        except TelegramNetworkError as e:
            logging.warning("delete_webhook failed (network timeout). Continue polling. Error: %s", e)

        await dp.start_polling(bot)
    finally:
        # В aiogram 3.4.x Bot не является async context manager, поэтому закрываем сессию вручную
        try:
            await bot.session.close()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
