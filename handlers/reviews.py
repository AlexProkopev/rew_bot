# telegram_reviews_bot/handlers/reviews.py
"""Handlers for creating new user reviews."""

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import os
import uuid
from pathlib import Path
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from handlers.admin import get_admin_review_keyboard
import database as db
from config import ADMIN_ID
from utils.loader import CallbackLoadingAnimation, loading_photo_upload

router = Router()


class ReviewState(StatesGroup):
    waiting_for_review_text = State()
    waiting_for_rating = State()
    waiting_for_review_photo = State()


cancel_button = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_review")
skip_photo_button = InlineKeyboardButton(text="Без фото", callback_data="skip_photo")


@router.message(F.text == "✍️ Оставить отзыв")
async def start_review(message: Message, state: FSMContext):
    await state.set_state(ReviewState.waiting_for_review_text)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[cancel_button]])
    await message.answer("Напишите текст вашего отзыва. Вы можете прикрепить одно фото на следующем шаге.", reply_markup=keyboard)


@router.callback_query(F.data == "cancel_review")
async def cancel_review(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отправка отзыва отменена.")
    await callback.answer()


@router.message(ReviewState.waiting_for_review_text, F.text)
async def review_text_received(message: Message, state: FSMContext):
    await state.update_data(review_text=message.text)
    await state.set_state(ReviewState.waiting_for_rating)

    rating_buttons: list[list[InlineKeyboardButton]] = []
    for rating in range(1, 6):
        stars = "⭐" * rating
        rating_buttons.append(
            [InlineKeyboardButton(text=f"{stars} ({rating})", callback_data=f"rating_{rating}")]
        )
    rating_buttons.append([cancel_button])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rating_buttons)
    await message.answer("Отлично! Теперь оцените магазин от 1 до 5 звезд:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("rating_"), ReviewState.waiting_for_rating)
async def rating_received(callback: CallbackQuery, state: FSMContext):
    rating = int(callback.data.split("_")[1])
    await state.update_data(rating=rating)
    await state.set_state(ReviewState.waiting_for_review_photo)

    stars = "⭐" * rating
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[skip_photo_button], [cancel_button]])
    await callback.message.edit_text(
        f"Отлично! Вы поставили {stars} ({rating}/5).\n\nТеперь отправьте фото для отзыва или нажмите «Без фото».",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "skip_photo", ReviewState.waiting_for_review_photo)
async def skip_photo_step(callback: CallbackQuery, state: FSMContext, bot: Bot):
    loader = CallbackLoadingAnimation(callback, "Отправляем отзыв")
    await loader.start()

    try:
        data = await state.get_data()
        review_text = data.get("review_text")
        rating = data.get("rating", 5)
        user = callback.from_user

        review_id = await db.add_review(user.id, user.username, review_text, rating=rating)

        await db.log_user_activity(user.id, "review_created")
        await state.clear()

        admin_kb = get_admin_review_keyboard(review_id)
        stars = "⭐" * rating
        await bot.send_message(
            ADMIN_ID,
            f"Новый отзыв на проверку от @{user.username}:\n{stars} ({rating}/5)\n\n{review_text}",
            reply_markup=admin_kb,
        )

        await loader.stop("✅ Спасибо! Ваш отзыв отправлен на проверку.")
    except Exception as error:
        await loader.stop("❌ Ошибка отправки отзыва")
        await callback.answer()
        raise error
    else:
        await callback.answer()


@router.message(ReviewState.waiting_for_review_photo, F.photo)
async def review_photo_received(message: Message, state: FSMContext, bot: Bot):
    loading_msg = await message.answer("🔄 Обрабатываем фото и отправляем отзыв...")
    loader = await loading_photo_upload(loading_msg)

    try:
        data = await state.get_data()
        review_text = data.get("review_text")
        rating = data.get("rating", 5)
        user = message.from_user
        photo = message.photo[-1]

        # Сохраняем файл локально, чтобы фото было доступно даже при смене токена бота
        media_dir = Path("media/photos")
        media_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex}.jpg"
        file_path = media_dir / unique_name

        # Скачиваем файл и сохраняем
        photo_file = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(photo_file.file_path)
        with open(file_path, "wb") as f:
            f.write(photo_bytes.read())

        stars = "⭐" * rating
        caption = f"Новый отзыв на проверку от @{user.username}:\n{stars} ({rating}/5)\n\n{review_text}"
        sent_photo = await bot.send_photo(chat_id=ADMIN_ID, photo=photo.file_id, caption=caption)

        review_id = await db.add_review(
            user.id,
            user.username,
            review_text,
            photo_id=photo.file_id,
            photo_path=str(file_path),
            rating=rating,
        )

        await db.log_user_activity(user.id, "review_with_photo_created")
        await state.clear()

        admin_kb = get_admin_review_keyboard(review_id)
        await bot.edit_message_caption(
            chat_id=ADMIN_ID,
            message_id=sent_photo.message_id,
            caption=caption,
            reply_markup=admin_kb,
        )

        await loader.stop("✅ Спасибо! Ваш отзыв отправлен на проверку.")
    except Exception as error:
        await loader.stop("❌ Ошибка отправки фото")
        raise error


# Обработчик для пользователей, которые присылают фото заново по запросу (в подписи указывают id отзыва)
@router.message(F.photo)
async def handle_resend_photo(message: Message, bot: Bot):
    caption = (message.caption or "").strip()
    import re
    m = re.search(r"(?:Resend review|Переслать отзыв)\s*#?(\d+)", caption, flags=re.IGNORECASE)
    if not m:
        return  # не наш маркер — это обычное фото

    review_id = int(m.group(1))
    photo = message.photo[-1]
    user = message.from_user

    # Сохраняем локальную копию
    media_dir = Path("media/photos")
    media_dir.mkdir(parents=True, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}.jpg"
    file_path = media_dir / unique_name

    try:
        file_obj = await bot.get_file(photo.file_id)
        file_bytes = await bot.download_file(file_obj.file_path)
        with open(file_path, "wb") as f:
            f.write(file_bytes.read())

        # Обновляем запись в БД
        await db.update_review_photo(review_id, photo.file_id, str(file_path))

        await message.answer(f"✅ Спасибо! Фото для отзыва #{review_id} сохранено.")
        # Уведомим админа, если нужно
        try:
            await bot.send_message(ADMIN_ID, f"Фото для отзыва #{review_id} обновлено пользователем @{user.username}.")
        except Exception:
            pass
    except Exception as e:
        await message.answer("❌ Не удалось сохранить фото. Попробуйте ещё раз или свяжитесь с админом.")
        print(f"Ошибка при сохранении пересланного фото для отзыва {review_id}: {e}")
