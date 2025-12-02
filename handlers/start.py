# telegram_reviews_bot/handlers/start.py
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart
import database as db
from config import ADMIN_ID

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await db.add_or_update_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name
    )
    
    kb = [
        [KeyboardButton(text="✍️ Оставить отзыв")],
        [KeyboardButton(text="👀 Посмотреть отзывы")]
    ]
    
    if message.from_user.id == ADMIN_ID:
        kb.append([KeyboardButton(text="👑 Админ-панель")])

    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        "👋 Привет! Я бот для сбора отзывов магазина Матрёшек. Вы можете оставить свой отзыв или посмотреть отзывы других.(Помни, каждый твой 10й отзыв = скидка 20% на следующую покупку)",
        reply_markup=keyboard
    )


# Контакты удалены — кнопка и обработчик убраны
