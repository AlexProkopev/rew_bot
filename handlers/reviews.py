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
from utils.loader import CallbackLoadingAnimation, loading_photo_upload

router = Router()

class ReviewState(StatesGroup):
    waiting_for_review_text = State()
    waiting_for_rating = State()
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

# --- Обработка выбора рейтинга ---
@router.callback_query(F.data.startswith("rating_"), ReviewState.waiting_for_rating)
async def rating_received(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])
    await state.update_data(rating=rating)
    await state.set_state(ReviewState.waiting_for_review_photo)
    
    stars = "⭐" * rating
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[skip_photo_button], [cancel_button]])
    await callback.message.edit_text(
        f"Отлично! Вы поставили {stars} ({rating}/5).\n\nТеперь отправьте фото для отзыва или нажмите «Без фото».", 
        reply_markup=keyboard
    )
    await callback.answer()

# --- Получение текста отзыва ---
@router.message(ReviewState.waiting_for_review_text, F.text)
async def review_text_received(message: Message, state: FSMContext):
    await state.update_data(review_text=message.text)
    await state.set_state(ReviewState.waiting_for_rating)
    
    # Создаем клавиатуру для выбора рейтинга
    rating_buttons = []
    for i in range(1, 6):
        stars = "⭐" * i
        rating_buttons.append([InlineKeyboardButton(text=f"{stars} ({i})", callback_data=f"rating_{i}")])
    
    rating_buttons.append([cancel_button])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rating_buttons)
    
    await message.answer("Отлично! Теперь оцените магазин от 1 до 5 звезд:", reply_markup=keyboard)

# --- Пропуск фото ---
@router.callback_query(F.data == "skip_photo", ReviewState.waiting_for_review_photo)
async def skip_photo_step(callback: CallbackQuery, state: FSMContext, bot: Bot):
    # Показываем лоадер
    loader = CallbackLoadingAnimation(callback, "Отправляем отзыв")
    await loader.start()
    
    try:
        data = await state.get_data()
        review_text = data.get("review_text")
        rating = data.get("rating", 5)
        user = callback.from_user
        
        review_id = await db.add_review(user.id, user.username, review_text, rating=rating)
        
        # Логируем создание отзыва
        await db.log_user_activity(user.id, "review_created")
        
        await state.clear()
        
        # Уведомление админу с кнопкой удаления
        admin_kb = get_admin_review_keyboard(review_id)
        stars = "⭐" * rating
        await bot.send_message(
            ADMIN_ID,
            f"Новый отзыв на проверку от @{user.username}:\n{stars} ({rating}/5)\n\n{review_text}",
            reply_markup=admin_kb
        )
        
        await loader.stop("✅ Спасибо! Ваш отзыв отправлен на проверку.")
        
    except Exception as e:
        await loader.stop("❌ Ошибка отправки отзыва")
        raise e
        
    await callback.answer()

# --- Получение фото ---
@router.message(ReviewState.waiting_for_review_photo, F.photo)
async def review_photo_received(message: Message, state: FSMContext, bot: Bot):
    # Отправляем сообщение с лоадером
    loading_msg = await message.answer("🔄 Обрабатываем фото и отправляем отзыв...")
    loader = await loading_photo_upload(loading_msg)
    
    try:
        data = await state.get_data()
        review_text = data.get("review_text")
        rating = data.get("rating", 5)
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
        stars = "⭐" * rating
        sent_photo = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=input_file,
            caption=f"Новый отзыв на проверку от @{user.username}:\n{stars} ({rating}/5)\n\n{review_text}"
        )
        
        # Сохраняем оригинальный file_id в БД
        review_id = await db.add_review(user.id, user.username, review_text, photo_id=photo.file_id, rating=rating)
        
        # Логируем создание отзыва с фото
        await db.log_user_activity(user.id, "review_with_photo_created")
        
        await state.clear()
        
        # Клавиатура для админа с кнопкой удаления
        admin_kb = get_admin_review_keyboard(review_id)
        await bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=sent_photo.message_id,
            caption=sent_photo.caption,
            reply_markup=admin_kb
        )
        
        await loader.stop("✅ Спасибо! Ваш отзыв с фото отправлен на проверку.")
        
    except Exception as e:
        await loader.stop("❌ Ошибка обработки фото")
        raise e
