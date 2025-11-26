# telegram_reviews_bot/handlers/start.py
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
import database as db
from config import ADMIN_ID

router = Router()

CONTACTS = [
    {"text": "Дарья", "url": "https://t.me/Matreshka_Dasha"},
    {"text": "Ольга", "url": "https://t.me/matreshka_olya"},
    {"text": "Сайт", "url": "https://clck.ru/3QWhgv"},
]

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
        [KeyboardButton(text="👀 Посмотреть отзывы")],
        [KeyboardButton(text="📞 Наши контакты")]
    ]
    
    if message.from_user.id == ADMIN_ID:
        kb.append([KeyboardButton(text="👑 Админ-панель")])

    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    
    await message.answer(
        "👋 Привет! Я бот для сбора отзывов. Вы можете оставить свой отзыв или посмотреть отзывы других.",
        reply_markup=keyboard
    )


@router.message(F.text == "📞 Наши контакты")
async def show_contacts(message: Message):
    buttons = [
        [InlineKeyboardButton(text=contact["text"], url=contact["url"])]
        for contact in CONTACTS
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Наши контакты:", reply_markup=keyboard)
