# telegram_reviews_bot/handlers/reviews.py
import io
from PIL import Image, ImageFilter
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from handlers.admin import get_admin_review_keyboard
import database as db
from config import ADMIN_ID

router = Router()

class ReviewState(StatesGroup):
    waiting_for_review_text = State()
    waiting_for_review_photo = State()

# --- Клавиатуры ---
cancel_button = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_review")
skip_photo_button = InlineKeyboardButton(text="Без фото", callback_data="skip_photo")

# --- Начало процесса отзыва ---
@router.message(F.text == "✍️ Оставить отзыв")
async def start_review(message: Message, state: FSMContext):
    await state.set_state(ReviewState.waiting_for_review_text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[cancel_button]])
    await message.answer("Напишите текст вашего отзыва. Вы можете прикрепить одно фото на следующем шаге.", reply_markup=keyboard)

# --- Отмена ---
@router.callback_query(F.data == "cancel_review")
async def cancel_review(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отправка отзыва отменена.")
    await callback.answer()

# --- Получение текста отзыва ---
@router.message(ReviewState.waiting_for_review_text, F.text)
async def review_text_received(message: Message, state: FSMContext):
    await state.update_data(review_text=message.text)
    await state.set_state(ReviewState.waiting_for_review_photo)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[skip_photo_button], [cancel_button]])
    await message.answer("Отлично! Теперь отправьте фото для отзыва или нажмите «Без фото».", reply_markup=keyboard)

# --- Пропуск фото ---
@router.callback_query(F.data == "skip_photo", ReviewState.waiting_for_review_photo)
async def skip_photo_step(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    review_text = data.get("review_text")
    user = callback.from_user
    
    review_id = await db.add_review(user.id, user.username, review_text)
    
    # Логируем создание отзыва
    await db.log_user_activity(user.id, "review_created")
    
    await state.clear()
    await callback.message.edit_text("✅ Спасибо! Ваш отзыв отправлен на проверку.")
    
    # Уведомление админу с кнопкой удаления
    admin_kb = get_admin_review_keyboard(review_id)
    await bot.send_message(
        ADMIN_ID,
        f"Новый отзыв на проверку от @{user.username}:\n\n{review_text}",
        reply_markup=admin_kb
    )
    await callback.answer()

# --- Получение фото ---
@router.message(ReviewState.waiting_for_review_photo, F.photo)
async def review_photo_received(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    review_text = data.get("review_text")
    user = message.from_user
    photo = message.photo[-1]

    # Скачиваем фото
    photo_file = await bot.get_file(photo.file_id)
    photo_bytes = await bot.download_file(photo_file.file_path)

    # Размываем фото
    img = Image.open(photo_bytes)
    blurred_img = img.filter(ImageFilter.GaussianBlur(15))
    
    # Сохраняем размытое изображение в байты
    blurred_photo_stream = io.BytesIO()
    blurred_img.save(blurred_photo_stream, format='JPEG')
    blurred_photo_stream.seek(0)

    # Отправляем размытое фото админу и получаем его file_id
    blurred_photo_stream.seek(0)
    input_file = BufferedInputFile(blurred_photo_stream.read(), filename="blurred.jpg")
    sent_photo = await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=input_file,
        caption=f"Новый отзыв на проверку от @{user.username}:\n\n{review_text}"
    )
    
    # Сохраняем оригинальный file_id в БД
    review_id = await db.add_review(user.id, user.username, review_text, photo_id=photo.file_id)
    
    # Логируем создание отзыва с фото
    await db.log_user_activity(user.id, "review_with_photo_created")
    
    await state.clear()
    await message.answer("✅ Спасибо! Ваш отзыв с фото отправлен на проверку.")

    # Клавиатура для админа с кнопкой удаления
    admin_kb = get_admin_review_keyboard(review_id)
    await bot.edit_message_caption(
        chat_id=ADMIN_ID,
        message_id=sent_photo.message_id,
        caption=sent_photo.caption,
        reply_markup=admin_kb
    )
