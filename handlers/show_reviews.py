# telegram_reviews_bot/handlers/show_reviews.py
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import ADMIN_ID
import database as db
from utils.loader import loading_reviews, loading_photo, loading_latest_reviews, LoadingAnimation


router = Router()

async def format_review_message(review):
    """Форматирует сообщение с отзывом."""
    rating = review.get('rating', 5)
    stars = "⭐" * rating
    username = review['username'] or 'аноним'
    photo_emoji = " 📸" if review['photo_id'] else ""
    text = f"Отзыв от: @{username}{photo_emoji}\n"
    text += f"Оценка: {stars} ({rating}/5)\n\n{review['text']}"
    return text

@router.message(F.text == "👀 Посмотреть отзывы")
async def show_reviews_cmd(message: Message, bot: Bot):
    # Показываем лоадер для обычного сообщения
    loader_msg = await message.answer("🔄 Загружаем отзывы...")
    loader = LoadingAnimation(loader_msg, "Загружаем отзывы")
    await loader.start()
    
    try:
        # Логируем просмотр отзывов
        await db.log_user_activity(message.from_user.id, "viewed_reviews")
        await show_reviews_page(message, bot, offset=0)
        await loader.stop()  # Останавливаем лоадер без финального текста
        
        # Удаляем сообщение с лоадером
        try:
            await loader_msg.delete()
        except:
            pass
            
    except Exception as e:
        await loader.stop("❌ Ошибка загрузки отзывов")
        raise e

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
        username = review['username'] or 'аноним'
        photo_emoji = " 📸" if review['photo_id'] else ""
        button_text = f"Отзыв №{review_number} от @{username}{photo_emoji}"
        # Передаем offset в callback_data для возврата на правильную страницу
        builder.button(text=button_text, callback_data=f"view_review_{review['id']}_{offset}")

    # Кнопка для показа последних 5 отзывов
    builder.button(text="📋 Последние 5 отзывов", callback_data="show_latest_5")

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
    text = f"📝 Отзывы ({total_reviews})\n"
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
    # Показываем лоадер
    loader = await loading_reviews(callback)
    
    try:
        offset = int(callback.data.split("_")[2])
        await show_reviews_page(callback, bot, offset)
        await loader.stop()  # Останавливаем лоадер без финального текста
    except Exception as e:
        await loader.stop("❌ Ошибка загрузки отзывов")
        raise e
    
    await callback.answer()

@router.callback_query(F.data.startswith("view_review_"))
async def view_single_review(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    review_id = int(parts[2])
    # Получаем offset, если он передан, иначе используем 0
    offset = int(parts[3]) if len(parts) > 3 else 0
    
    review = await db.get_review(review_id)

    if not review:
        await callback.answer("Отзыв не найден.", show_alert=True)
        return

    text = await format_review_message(review)
    keyboard = []
    if review['photo_id']:
        keyboard.append([InlineKeyboardButton(text="🖼️ Показать фото", callback_data=f"show_photo_{review_id}_{offset}")])
    if callback.from_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_review_{review_id}_{offset}")])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"reviews_page_{offset}")])
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
    parts = callback.data.split("_")
    review_id = int(parts[2])
    offset = int(parts[3]) if len(parts) > 3 else 0
    
    await db.delete_review(review_id)
    
    # Создаем кнопку для возврата на правильную страницу
    back_button = InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"reviews_page_{offset}")
    reply_markup = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
    
    await callback.message.edit_text(f"🗑️ Отзыв #{review_id} удалён.", reply_markup=reply_markup)
    await callback.answer("Отзыв удалён.", show_alert=True)

@router.callback_query(F.data.startswith("show_photo_"))
async def show_review_photo(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    review_id = int(parts[2])
    offset = int(parts[3]) if len(parts) > 3 else 0
    
    # Показываем лоадер
    loader = await loading_photo(callback)
    
    try:
        review = await db.get_review(review_id)

        if not review or not review['photo_id']:
            await loader.stop("❌ Фото не найдено")
            await callback.answer("Фото не найдено.", show_alert=True)
            return

        text = await format_review_message(review)
        # Кнопка для скрытия фото
        hide_button = InlineKeyboardButton(text="🙈 Скрыть фото", callback_data=f"hide_photo_{review_id}_{offset}")
        back_button = InlineKeyboardButton(text="⬅️ Назад к списку", callback_data=f"reviews_page_{offset}")
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
        
        await loader.stop()  # Останавливаем лоадер перед показом фото
        
        await callback.message.edit_media(
            media=InputMediaPhoto(media=input_file, caption=text),
            reply_markup=reply_markup
        )
        
    except Exception as e:
        await loader.stop("❌ Ошибка загрузки фото")
        raise e
        
    await callback.answer()

@router.callback_query(F.data.startswith("hide_photo_"))
async def hide_review_photo(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split("_")
    review_id = int(parts[2])
    offset = int(parts[3]) if len(parts) > 3 else 0
    
    # Создаем новый callback_data с правильным offset
    callback.data = f"view_review_{review_id}_{offset}"
    
    # Если текущее сообщение — фото, Telegram не даст заменить на текст, поэтому заменяем на "пустую" картинку с текстом
    await view_single_review(callback, bot)
    await callback.answer()

@router.callback_query(F.data == "show_latest_5")
async def show_latest_5_reviews(callback: CallbackQuery, bot: Bot):
    """Показывает последние 5 отзывов развернуто."""
    # Показываем лоадер
    loader = await loading_latest_reviews(callback)
    
    try:
        reviews = await db.get_approved_reviews(offset=0, limit=5)
        total_reviews = await db.count_approved_reviews()
        
        if not reviews:
            await loader.stop("❌ Пока нет ни одного одобренного отзыва")
            await callback.answer("Пока нет ни одного одобренного отзыва.", show_alert=True)
            return
    
        # Получаем среднюю оценку
        avg_rating = await db.get_average_rating()
        stars_display = "⭐" * int(round(avg_rating)) if avg_rating > 0 else "Нет оценок"
        
        # Формируем большое сообщение со всеми отзывами
        message_text = f"🌟 **Последние 5 отзывов**\n\n"
        message_text += f"📊 Всего: {total_reviews}\n"
        if avg_rating > 0:
            message_text += f"⭐ Средняя оценка: {stars_display} ({avg_rating:.1f}/5)\n\n"
        else:
            message_text += "⭐ Средняя оценка: пока нет оценок\n\n"
        
        message_text += "─" * 30 + "\n\n"
        
        for idx, review in enumerate(reviews, 1):
            review_number = total_reviews - idx + 1
            rating = review.get('rating', 5)
            stars = "⭐" * rating
            username = review['username'] or 'аноним'
            photo_emoji = " 📸" if review['photo_id'] else ""
            
            message_text += f"**{review_number}. Отзыв от @{username}{photo_emoji}**\n"
            message_text += f"Оценка: {stars} ({rating}/5)\n\n"
            message_text += f"{review['text']}\n"
            
            if review['photo_id']:
                message_text += "📸 *К отзыву прикреплено фото*\n"
            
            if idx < len(reviews):  # Не добавляем разделитель после последнего отзыва
                message_text += "\n" + "─" * 30 + "\n\n"
        
        # Кнопка для возврата к списку
        back_button = InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="reviews_page_0")
        reply_markup = InlineKeyboardMarkup(inline_keyboard=[[back_button]])
        
        # Проверяем длину сообщения (лимит Telegram ~4096 символов)
        if len(message_text) > 4000:
            await loader.stop("❌ Отзывы слишком длинные для одного сообщения")
            await callback.answer("Отзывы слишком длинные для одного сообщения. Используйте обычный просмотр.", show_alert=True)
            return
        
        # Останавливаем лоадер и показываем результат
        await loader.stop(message_text, reply_markup)
        
    except Exception as e:
        await loader.stop("❌ Ошибка загрузки отзывов")
        raise e
    
    await callback.answer()
