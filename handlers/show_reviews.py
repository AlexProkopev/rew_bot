# telegram_reviews_bot/handlers/show_reviews.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
import database as db


router = Router()

async def format_review_message(review):
    """Форматирует сообщение с отзывом."""
    rating = review.get('rating', 5)
    stars = "⭐" * rating
    text = f"Отзыв от: @{review['username'] or 'аноним'}\n"
    text += f"Оценка: {stars} ({rating}/5)\n\n{review['text']}"
    return text

@router.message(F.text == "👀 Посмотреть отзывы")
async def show_reviews_cmd(message: Message, bot: Bot):
    # Логируем просмотр отзывов
    await db.log_user_activity(message.from_user.id, "viewed_reviews")
    await show_reviews_page(message, bot, offset=0)

async def show_reviews_page(message_or_callback, bot: Bot, offset: int):
    """Отображает страницу с отзывами."""
    reviews = await db.get_approved_reviews(offset=offset, limit=5)
    total_reviews = await db.count_approved_reviews()

    if not reviews:
        await message_or_callback.answer("Пока нет ни одного одобренного отзыва.")
        return

    builder = InlineKeyboardBuilder()
    
    # Рассчитываем номера так, чтобы новые отзывы имели большие номера
    # total_reviews - offset даёт нам номер первого отзыва на текущей странице
    for idx, review in enumerate(reviews):
        review_number = total_reviews - offset - idx
        # Показываем порядковый номер на странице, а не id из базы
        button_text = f"Отзыв №{review_number} от @{review['username'] or 'аноним'}"
        builder.button(text=button_text, callback_data=f"view_review_{review['id']}")

    # Логика пагинации
    if offset > 0:
        builder.button(text="⬅️ Назад", callback_data=f"reviews_page_{offset - 5}")
    if offset + 5 < total_reviews:
        builder.button(text="Вперёд ➡️", callback_data=f"reviews_page_{offset + 5}")
    
    builder.adjust(1) # Все кнопки в один столбец

    # Получаем среднюю оценку
    avg_rating = await db.get_average_rating()
    stars_display = "⭐" * int(round(avg_rating)) if avg_rating > 0 else "Нет оценок"
    
    # Формируем текст с статистикой
    text = f"📝 Отзывы (всего одобрено: {total_reviews})\n"
    if avg_rating > 0:
        text += f"⭐ Средняя оценка: {stars_display} ({avg_rating:.1f}/5)"
    else:
        text += "⭐ Средняя оценка: пока нет оценок"
    
    # Определяем, откуда пришел запрос
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=builder.as_markup())
    elif isinstance(message_or_callback, CallbackQuery):
        msg = message_or_callback.message
        if msg.content_type == 'photo':
            from aiogram.types import InputMediaPhoto
            # Пустая картинка с текстом (Telegram требует media, иначе ошибка)
            await msg.edit_media(
                media=InputMediaPhoto(media="https://dummyimage.com/1x1/ffffff/ffffff", caption=text),
                reply_markup=builder.as_markup()
            )
        else:
            await msg.edit_text(text, reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("reviews_page_"))
async def paginate_reviews(callback: CallbackQuery, bot: Bot):
    offset = int(callback.data.split("_")[2])
    await show_reviews_page(callback, bot, offset)
    await callback.answer()

@router.callback_query(F.data.startswith("view_review_"))
async def view_single_review(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split("_")[2])
    review = await db.get_review(review_id)

    if not review:
        await callback.answer("Отзыв не найден.", show_alert=True)
        return

    text = await format_review_message(review)
    keyboard = []
    if review['photo_id']:
        keyboard.append([InlineKeyboardButton(text="🖼️ Показать фото", callback_data=f"show_photo_{review_id}")])
    if callback.from_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_review_{review_id}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="reviews_page_0")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    # Если текущее сообщение фото, заменяем на текст через edit_media
    if callback.message.content_type == 'photo':
        from aiogram.types import InputMediaPhoto
        # Пустая картинка с текстом (Telegram требует media, иначе ошибка)
        await callback.message.edit_media(
            media=InputMediaPhoto(media="https://dummyimage.com/1x1/ffffff/ffffff", caption=text),
            reply_markup=reply_markup
        )
    else:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()

# --- Обработчик удаления отзыва из просмотра ---
@router.callback_query(F.data.startswith("delete_review_"))
async def delete_review_from_view(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split("_")[2])
    await db.delete_review(review_id)
    await callback.message.edit_text(f"🗑️ Отзыв #{review_id} удалён.")
    await callback.answer("Отзыв удалён.", show_alert=True)

@router.callback_query(F.data.startswith("show_photo_"))
async def show_review_photo(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split("_")[2])
    review = await db.get_review(review_id)

    if not review or not review['photo_id']:
        await callback.answer("Фото не найдено.", show_alert=True)
        return

    text = await format_review_message(review)
    # Кнопка для скрытия фото
    hide_button = InlineKeyboardButton(text="🙈 Скрыть фото", callback_data=f"hide_photo_{review_id}")
    back_button = InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="reviews_page_0")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[hide_button], [back_button]])

    # Скачиваем фото, блюрим и отправляем как BufferedInputFile
    from aiogram.types import BufferedInputFile
    import io
    from PIL import Image, ImageFilter
    photo_file = await bot.get_file(review['photo_id'])
    photo_bytes = await bot.download_file(photo_file.file_path)
    img = Image.open(photo_bytes)
    blurred_img = img.filter(ImageFilter.GaussianBlur(15))
    blurred_photo_stream = io.BytesIO()
    blurred_img.save(blurred_photo_stream, format='JPEG')
    blurred_photo_stream.seek(0)
    input_file = BufferedInputFile(blurred_photo_stream.read(), filename="blurred.jpg")
    from aiogram.types import InputMediaPhoto
    await callback.message.edit_media(
        media=InputMediaPhoto(media=input_file, caption=text),
        reply_markup=reply_markup
    )
    await callback.answer()

@router.callback_query(F.data.startswith("hide_photo_"))
async def hide_review_photo(callback: CallbackQuery, bot: Bot):
    # Если текущее сообщение — фото, Telegram не даст заменить на текст, поэтому заменяем на "пустую" картинку с текстом
    await view_single_review(callback, bot)
    await callback.answer()
