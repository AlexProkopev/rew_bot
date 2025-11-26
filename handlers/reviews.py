# telegram_reviews_bot/handlers/reviews.py
"""Handlers for creating new user reviews."""

import io
from PIL import Image, ImageFilter
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from handlers.admin import get_admin_review_keyboard
import database as db
from config import ADMIN_ID
from utils.loader import CallbackLoadingAnimation, loading_photo_upload
from utils.products import PRODUCTS, get_product_title

router = Router()


class ReviewState(StatesGroup):
    waiting_for_product = State()
    waiting_for_review_text = State()
    waiting_for_rating = State()
    waiting_for_review_photo = State()


cancel_button = InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_review")
skip_photo_button = InlineKeyboardButton(text="Без фото", callback_data="skip_photo")


def _format_author(username: str | None, full_name: str | None, user_id: int) -> str:
    if username:
        return f"@{username}"
    if full_name:
        return full_name
    return str(user_id)


@router.message(F.text == "✍️ Оставить отзыв")
async def start_review(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ReviewState.waiting_for_product)

    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    for index, product in enumerate(PRODUCTS, start=1):
        current_row.append(
            InlineKeyboardButton(text=product["title"], callback_data=f"product_{product['code']}")
        )
        if index % 2 == 0:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([cancel_button])

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    await message.answer("Выберите товар, о котором хотите оставить отзыв:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("product_"), ReviewState.waiting_for_product)
async def product_selected(callback: CallbackQuery, state: FSMContext):
    product_code = callback.data.split("product_", maxsplit=1)[1]
    product_title = get_product_title(product_code)

    await state.update_data(product_code=product_code)
    await state.set_state(ReviewState.waiting_for_review_text)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[cancel_button]])
    await callback.message.edit_text(
        f"Вы выбрали: {product_title}.\nТеперь напишите текст вашего отзыва. Вы можете прикрепить одно фото на следующем шаге.",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_review")
async def cancel_review(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Отправка отзыва отменена.")
    await callback.answer()


@router.message(ReviewState.waiting_for_review_text, F.text)
async def review_text_received(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data.get("product_code"):
        await start_review(message, state)
        return

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
        product_code = data.get("product_code")
        product_title = get_product_title(product_code)
        rating = data.get("rating", 5)
        user = callback.from_user
        author = _format_author(user.username, user.full_name, user.id)

        review_id = await db.add_review(
            user.id,
            user.username,
            review_text,
            photo_id=None,
            blurred_photo_id=None,
            rating=rating,
            product_code=product_code,
        )

        await db.log_user_activity(user.id, "review_created")
        await state.clear()

        admin_kb = get_admin_review_keyboard(review_id)
        stars = "⭐" * rating
        await bot.send_message(
            ADMIN_ID,
            f"Новый отзыв на проверку от {author}:\n"
            f"Товар: {product_title}\n"
            f"{stars} ({rating}/5)\n\n"
            f"{review_text}",
            reply_markup=admin_kb,
        )

        await loader.stop(f"✅ Спасибо! Ваш отзыв о {product_title} отправлен на проверку.")
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
        product_code = data.get("product_code")
        product_title = get_product_title(product_code)
        rating = data.get("rating", 5)
        user = message.from_user
        author = _format_author(user.username, user.full_name, user.id)
        photo = message.photo[-1]

        photo_file = await bot.get_file(photo.file_id)
        photo_bytes = await bot.download_file(photo_file.file_path)

        img = Image.open(photo_bytes)
        blurred_img = img.filter(ImageFilter.GaussianBlur(15))

        blurred_photo_stream = io.BytesIO()
        blurred_img.save(blurred_photo_stream, format="JPEG")
        blurred_photo_stream.seek(0)

        input_file = BufferedInputFile(blurred_photo_stream.read(), filename="blurred.jpg")
        stars = "⭐" * rating
        caption = (
            f"Новый отзыв на проверку от {author}:\n"
            f"Товар: {product_title}\n"
            f"{stars} ({rating}/5)\n\n"
            f"{review_text}"
        )
        sent_photo = await bot.send_photo(chat_id=ADMIN_ID, photo=input_file, caption=caption)
        blurred_file_id = sent_photo.photo[-1].file_id if sent_photo.photo else None

        review_id = await db.add_review(
            user.id,
            user.username,
            review_text,
            photo_id=photo.file_id,
            blurred_photo_id=blurred_file_id,
            rating=rating,
            product_code=product_code,
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

        await loader.stop(f"✅ Спасибо! Ваш отзыв о {product_title} с фото отправлен на проверку.")
    except Exception as error:
        await loader.stop("❌ Ошибка обработки фото")
        raise error
