# telegram_reviews_bot/bot.py
import asyncio
import logging
import socket
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import ClientTimeout, TCPConnector

from config import BOT_TOKEN
import database as db
from handlers import start, reviews, admin, show_reviews

async def main():
    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    
    # Инициализация базы данных
    await db.init_db()

    # Инициализация диспетчера
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(reviews.router)
    dp.include_router(show_reviews.router)
    dp.include_router(admin.router) # Админский роутер должен быть последним, чтобы его фильтры не мешали другим

    # На Render иногда бывает сетевой таймаут до api.telegram.org (особенно при IPv6/маршрутизации).
    # Чтобы воркер не "умирал", делаем корректную настройку сессии и перезапуск поллинга при сетевых ошибках.
    reconnect_delay_sec = 15
    while True:
        bot = Bot(
            token=BOT_TOKEN,
            default=DefaultBotProperties(parse_mode="HTML"),
            session=AiohttpSession(
                timeout=ClientTimeout(total=75),
                connector=TCPConnector(family=socket.AF_INET),
            ),
        )
        try:
            # Удаление вебхука и запуск поллинга
            try:
                await bot.delete_webhook(drop_pending_updates=True, request_timeout=60)
            except TelegramNetworkError as e:
                logging.warning(
                    "delete_webhook failed (network timeout). Continue polling. Error: %s", e
                )

            await dp.start_polling(bot)
            # Если polling остановился штатно (например, сигнал остановки), выходим.
            break
        except TelegramNetworkError as e:
            logging.error(
                "Telegram network error; retry polling in %ss. Error: %s",
                reconnect_delay_sec,
                e,
            )
            await asyncio.sleep(reconnect_delay_sec)
        finally:
            # В aiogram 3.4.x Bot не является async context manager, поэтому закрываем сессию вручную
            try:
                await bot.session.close()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
