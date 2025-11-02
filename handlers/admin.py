# telegram_reviews_bot/handlers/admin.py
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Filter
import database as db
from config import ADMIN_ID

# --- Фильтр для проверки админа ---
class AdminFilter(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id == ADMIN_ID

router = Router()
router.message.filter(AdminFilter()) # Применяем фильтр ко всем хендлерам в этом роутере

# --- Состояния для FSM ---
class AdminState(StatesGroup):
    # Рассылка
    mailing_message = State()
    mailing_confirmation = State()
    # Шаблоны
    template_name = State()
    template_text = State()
    # Поиск пользователя
    user_search_query = State()
    # Сообщение пользователю
    message_to_user_text = State()
    
# --- Главное меню админа ---
@router.message(F.text == "👑 Админ-панель")
async def admin_panel(message: Message):
    kb = [
        [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="📢 Рассылка"), KeyboardButton(text="📝 Шаблоны сообщений")],
        [KeyboardButton(text="⬅️ Назад в главное меню")]
    ]
    keyboard = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)
    await message.answer("Добро пожаловать в админ-панель!", reply_markup=keyboard)

@router.message(F.text == "⬅️ Назад в главное меню")
async def back_to_main_menu(message: Message):
    from handlers.start import cmd_start # Избегаем циклического импорта
    await cmd_start(message)

# --- Быстрое добавление отзыва через пересылку ---
@router.message(F.forward_from)
async def forward_as_review(message: Message, bot: Bot):
    """Админ пересылает сообщение — оно сохраняется как одобренный отзыв"""
    forwarded_user = message.forward_from
    
    # Если пересланное сообщение от пользователя со скрытой пересылкой, не обработаем
    if not forwarded_user:
        await message.answer("⚠️ Не могу получить данные отправителя (возможно, у пользователя скрыта пересылка). Отзыв не добавлен.")
        return
    
    # Извлекаем текст и фото
    text = message.text or message.caption or ""
    photo_id = None
    
    if message.photo:
        photo_id = message.photo[-1].file_id
    
    if not text and not photo_id:
        await message.answer("⚠️ Сообщение не содержит текста или фото. Отзыв не добавлен.")
        return
    
    # Сохраняем пользователя в БД
    await db.add_or_update_user(
        user_id=forwarded_user.id,
        username=forwarded_user.username,
        first_name=forwarded_user.first_name,
        last_name=forwarded_user.last_name
    )
    
    # Добавляем отзыв сразу как одобренный с рейтингом 5 звезд
    review_id = await db.add_review(
        user_id=forwarded_user.id,
        username=forwarded_user.username,
        text=text,
        photo_id=photo_id,
        rating=5  # Автоматически ставим 5 звезд для пересылаемых отзывов
    )
    await db.update_review_status(review_id, "approved")
    
    # Подтверждение админу
    confirm_text = f"✅ Отзыв #{review_id} добавлен и одобрен!\n\n"
    confirm_text += f"От: @{forwarded_user.username or forwarded_user.first_name}\n"
    confirm_text += f"Оценка: ⭐⭐⭐⭐⭐ (5/5) - автоматически\n"
    if text:
        confirm_text += f"Текст: {text[:100]}{'...' if len(text) > 100 else ''}"
    if photo_id:
        confirm_text += f"\n🖼️ С фото"
    
    await message.answer(confirm_text)

# --- Обработка модерации отзывов ---

# --- Кнопки для модерации с удалением ---
def get_admin_review_keyboard(review_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"admin_approve_{review_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"admin_reject_{review_id}")],
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin_delete_{review_id}")]
    ])

@router.callback_query(F.data.startswith("admin_approve_"))
async def approve_review(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split("_")[2])
    review = await db.get_review(review_id)
    if not review:
        await callback.message.edit_text("Отзыв уже был обработан.")
        await callback.answer()
        return

    await db.update_review_status(review_id, "approved")
    if callback.message.content_type == "photo":
        await callback.message.edit_caption(f"✅ Отзыв #{review_id} одобрен.")
    else:
        await callback.message.edit_text(f"✅ Отзыв #{review_id} одобрен.")
    try:
        await bot.send_message(review['user_id'], "Ваш отзыв был одобрен и опубликован!")
    except Exception as e:
        print(f"Не удалось уведомить пользователя {review['user_id']}: {e}")
    await callback.answer()

@router.callback_query(F.data.startswith("admin_delete_"))
async def delete_review_callback(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split("_")[2])
    await db.delete_review(review_id)
    await callback.message.edit_text(f"🗑️ Отзыв #{review_id} удалён.")
    await callback.answer("Отзыв удалён.", show_alert=True)

@router.callback_query(F.data.startswith("admin_reject_"))
async def reject_review(callback: CallbackQuery, bot: Bot):
    review_id = int(callback.data.split("_")[2])
    review = await db.get_review(review_id)
    if not review:
        await callback.message.edit_text("Отзыв уже был обработан.")
        await callback.answer()
        return
    await db.update_review_status(review_id, "rejected")
    if callback.message.content_type == "photo":
        await callback.message.edit_caption(f"❌ Отзыв #{review_id} отклонен.")
    else:
        await callback.message.edit_text(f"❌ Отзыв #{review_id} отклонен.")
    try:
        await bot.send_message(review['user_id'], "К сожалению, ваш отзыв был отклонен.")
    except Exception as e:
        print(f"Не удалось уведомить пользователя {review['user_id']}: {e}")
    await callback.answer()

# --- Управление пользователями ---
@router.message(F.text == "👥 Пользователи")
async def show_users_menu(message: Message, state: FSMContext):
    await state.clear() # Сбрасываем состояние на случай, если админ был в другом меню
    await display_users_page(message)

async def display_users_page(message_or_callback, page=1, search_query=None):
    users, total = await db.get_all_users(page=page, limit=5, search_query=search_query)
    
    if not users:
        text = "Пользователи не найдены."
        if search_query:
            text += f"\nПо запросу: `{search_query}`"
        await message_or_callback.answer(text)
        return

    text = f"👥 Пользователи (Страница {page}):\n\n"
    
    inline_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"@{user['username'] or user['first_name']}", callback_data=f"user_details_{user['user_id']}")] for user in users
        ]
    )
    
    # Пагинация
    pagination_buttons = []
    if page > 1:
        pagination_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"users_page_{page-1}_{search_query or ''}"))
    if total > page * 5:
        pagination_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"users_page_{page+1}_{search_query or ''}"))
    
    # Кнопка поиска
    search_button = InlineKeyboardButton(text="🔍 Поиск", callback_data="search_user")
    
    # Собираем клавиатуру
    keyboard = inline_kb.inline_keyboard
    if pagination_buttons:
        keyboard.append(pagination_buttons)
    keyboard.append([search_button])
    
    final_markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if isinstance(message_or_callback, Message):
        await message_or_callback.answer(text, reply_markup=final_markup)
    else: # CallbackQuery
        await message_or_callback.message.edit_text(text, reply_markup=final_markup)

@router.callback_query(F.data.startswith("users_page_"))
async def paginate_users(callback: CallbackQuery):
    parts = callback.data.split("_")
    page = int(parts[2])
    search_query = parts[3] if len(parts) > 3 and parts[3] else None
    await display_users_page(callback, page=page, search_query=search_query)
    await callback.answer()

@router.callback_query(F.data == "search_user")
async def search_user_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.user_search_query)
    await callback.message.edit_text("Введите имя или username для поиска:")
    await callback.answer()

@router.message(AdminState.user_search_query)
async def process_user_search(message: Message, state: FSMContext):
    await state.clear()
    await display_users_page(message, page=1, search_query=message.text)

@router.callback_query(F.data.startswith("user_details_"))
async def user_details(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[2])
    await state.update_data(target_user_id=user_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать сообщение", callback_data="write_to_user")],
        [InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="back_to_users_list")]
    ])
    await callback.message.edit_text(f"Действия для пользователя ID: {user_id}", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_users_list")
async def back_to_users(callback: CallbackQuery):
    await display_users_page(callback, page=1)
    await callback.answer()

@router.callback_query(F.data == "write_to_user")
async def write_to_user_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.message_to_user_text)
    await callback.message.edit_text("Введите текст сообщения для этого пользователя:")
    await callback.answer()

@router.message(AdminState.message_to_user_text)
async def send_message_to_user(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    user_id = data.get("target_user_id")
    await state.clear()
    
    try:
        await bot.send_message(user_id, f"Сообщение от администратора:\n\n{message.text}")
        await message.answer("✅ Сообщение успешно отправлено.")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение: {e}")
    
    # Возвращаемся к меню пользователей
    await show_users_menu(message, state)

# --- Рассылка ---
@router.message(F.text == "📢 Рассылка")
async def mailing_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.mailing_message)
    
    templates = await db.get_all_templates()
    kb_list = [[KeyboardButton(text="❌ Отмена")]]
    if templates:
        kb_list.insert(0, [KeyboardButton(text="Использовать шаблон")])
        
    kb = ReplyKeyboardMarkup(keyboard=kb_list, resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Введите сообщение для рассылки. Вы можете использовать форматирование.", reply_markup=kb)

@router.message(F.text == "Использовать шаблон", AdminState.mailing_message)
async def use_template_for_mailing(message: Message, state: FSMContext):
    templates = await db.get_all_templates()
    if not templates:
        await message.answer("Нет сохраненных шаблонов.")
        return
    
    buttons = [InlineKeyboardButton(text=t['name'], callback_data=f"use_template_{t['name']}") for t in templates]
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await message.answer("Выберите шаблон:", reply_markup=kb)

@router.callback_query(F.data.startswith("use_template_"), AdminState.mailing_message)
async def apply_template_for_mailing(callback: CallbackQuery, state: FSMContext):
    template_name = callback.data.split("_")[2]
    template = await db.get_template(template_name)
    if template:
        await state.update_data(mailing_message=template['text'])
        await state.set_state(AdminState.mailing_confirmation)
        await callback.message.edit_text(f"Будет отправлено сообщение:\n\n{template['text']}\n\nОтправляем?",
                                        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                            [InlineKeyboardButton(text="✅ Да, отправить", callback_data="confirm_mailing")],
                                            [InlineKeyboardButton(text="❌ Нет, отмена", callback_data="cancel_mailing")]
                                        ]))
    else:
        await callback.message.edit_text("Шаблон не найден.")
    await callback.answer()


@router.message(AdminState.mailing_message)
async def mailing_message_received(message: Message, state: FSMContext):
    await state.update_data(mailing_message=message.text)
    await state.set_state(AdminState.mailing_confirmation)
    await message.answer(f"Сообщение для рассылки:\n\n{message.text}\n\nВсе верно?",
                         reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                             [InlineKeyboardButton(text="✅ Да, начать рассылку", callback_data="confirm_mailing")],
                             [InlineKeyboardButton(text="❌ Нет, ввести заново", callback_data="retry_mailing")]
                         ]))

@router.callback_query(F.data == "retry_mailing", AdminState.mailing_confirmation)
async def mailing_retry(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.mailing_message)
    await callback.message.edit_text("Введите новое сообщение для рассылки:")
    await callback.answer()

@router.callback_query(F.data == "confirm_mailing", AdminState.mailing_confirmation)
async def mailing_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    text = data.get("mailing_message")
    await state.clear()
    
    user_ids = await db.get_all_user_ids()
    
    await callback.message.edit_text(f"Начинаю рассылку... Всего пользователей: {len(user_ids)}")
    
    sent_count = 0
    failed_count = 0
    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            sent_count += 1
            await asyncio.sleep(0.1) # Чтобы не превышать лимиты Telegram
        except Exception:
            failed_count += 1
            
    await callback.message.answer(f"✅ Рассылка завершена!\n\nОтправлено: {sent_count}\nНе удалось отправить: {failed_count}")
    await admin_panel(callback.message) # Возвращаемся в админ-панель

@router.callback_query(F.data == "cancel_mailing", AdminState.mailing_confirmation)
@router.message(F.text == "❌ Отмена", AdminState.mailing_message)
async def mailing_cancel(message_or_callback: Message | CallbackQuery, state: FSMContext):
    await state.clear()
    if isinstance(message_or_callback, Message):
        await message_or_callback.answer("Рассылка отменена.")
        await admin_panel(message_or_callback)
    else: # CallbackQuery
        await message_or_callback.message.edit_text("Рассылка отменена.")
        await admin_panel(message_or_callback.message)


# --- Шаблоны ---
@router.message(F.text == "📝 Шаблоны сообщений")
async def templates_menu(message: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Создать новый шаблон", callback_data="create_template")],
        [InlineKeyboardButton(text="Посмотреть шаблоны", callback_data="view_templates")]
    ])
    await message.answer("Управление шаблонами:", reply_markup=kb)

@router.callback_query(F.data == "create_template")
async def create_template_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.template_name)
    await callback.message.edit_text("Введите название для нового шаблона (например, `приветствие`):")
    await callback.answer()

@router.message(AdminState.template_name)
async def template_name_received(message: Message, state: FSMContext):
    await state.update_data(template_name=message.text)
    await state.set_state(AdminState.template_text)
    await message.answer("Теперь введите текст шаблона:")

@router.message(AdminState.template_text)
async def template_text_received(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data.get("template_name")
    text = message.text
    
    await db.add_template(name, text)
    await state.clear()
    await message.answer(f"✅ Шаблон '{name}' успешно сохранен.")
    await templates_menu(message)

@router.callback_query(F.data == "view_templates")
async def view_templates_list(callback: CallbackQuery):
    templates = await db.get_all_templates()
    if not templates:
        await callback.message.edit_text("Нет сохраненных шаблонов.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_templates_menu")]]))
        await callback.answer()
        return

    buttons = [InlineKeyboardButton(text=t['name'], callback_data=f"view_template_detail_{t['name']}") for t in templates]
    buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_templates_menu"))
    kb = InlineKeyboardMarkup(inline_keyboard=[buttons])
    await callback.message.edit_text("Сохраненные шаблоны:", reply_markup=kb)
    await callback.answer()

@router.callback_query(F.data == "back_to_templates_menu")
async def back_to_templates_menu(callback: CallbackQuery):
    # Это действие просто заново вызывает меню шаблонов
    await templates_menu(callback.message)
    await callback.answer()

@router.callback_query(F.data.startswith("view_template_detail_"))
async def view_template_detail(callback: CallbackQuery):
    name = callback.data.split("_")[3]
    template = await db.get_template(name)
    if template:
        await callback.message.edit_text(f"Шаблон: **{template['name']}**\n\n{template['text']}", parse_mode="Markdown")
    else:
        await callback.message.edit_text("Шаблон не найден.")
    await callback.answer()

# --- Статистика ---
@router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    # Получаем все данные параллельно
    total_users = await db.get_total_users_count()
    total_reviews = await db.get_total_reviews_count()
    approved_reviews = await db.count_approved_reviews()
    daily_new_users = await db.get_daily_new_users()
    daily_reviews = await db.get_daily_reviews()
    active_today = await db.get_active_users_today()
    inactive_users = await db.get_inactive_users_count()
    reviews_by_status = await db.get_reviews_by_status()
    avg_rating = await db.get_average_rating()
    rating_distribution = await db.get_rating_distribution()
    
    # Формируем статистику
    stats_text = "📊 **Статистика бота**\n\n"
    
    # Общие данные
    stats_text += f"👥 **Пользователи:**\n"
    stats_text += f"• Всего зарегистрировано: {total_users}\n"
    stats_text += f"• Новых сегодня: {daily_new_users}\n"
    stats_text += f"• Активных сегодня: {active_today}\n"
    stats_text += f"• Неактивных (>7 дней): {inactive_users}\n\n"
    
    # Отзывы
    stats_text += f"📝 **Отзывы:**\n"
    stats_text += f"• Всего получено: {total_reviews}\n"
    stats_text += f"• Одобрено: {approved_reviews}\n"
    stats_text += f"• Получено сегодня: {daily_reviews}\n\n"
    
    # Рейтинги
    if avg_rating > 0:
        stars_display = "⭐" * int(round(avg_rating))
        stats_text += f"⭐ **Оценки:**\n"
        stats_text += f"• Средняя оценка: {stars_display} ({avg_rating:.1f}/5)\n"
        
        if rating_distribution:
            stats_text += "• Распределение:\n"
            for rating in sorted(rating_distribution.keys(), reverse=True):
                count = rating_distribution[rating]
                stars = "⭐" * rating
                stats_text += f"  {stars} ({rating}): {count} отз.\n"
        stats_text += "\n"
    
    # Статистика по статусам отзывов
    if reviews_by_status:
        stats_text += "📋 **По статусам:**\n"
        status_names = {
            'pending': '⏳ На модерации',
            'approved': '✅ Одобрено',
            'rejected': '❌ Отклонено'
        }
        for status, count in reviews_by_status.items():
            status_name = status_names.get(status, status)
            stats_text += f"• {status_name}: {count}\n"
    
    # Кнопки для дополнительных действий
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="refresh_stats")],
        [InlineKeyboardButton(text="📈 Детальная статистика", callback_data="detailed_stats")]
    ])
    
    await message.answer(stats_text, parse_mode="Markdown", reply_markup=kb)

@router.callback_query(F.data == "refresh_stats")
async def refresh_statistics(callback: CallbackQuery):
    await show_statistics(callback.message)
    await callback.answer("Статистика обновлена!")

@router.callback_query(F.data == "detailed_stats")
async def show_detailed_statistics(callback: CallbackQuery):
    # Здесь можно добавить более подробную статистику
    # Например, графики активности по дням, топ пользователей и т.д.
    
    detailed_text = "📈 **Детальная статистика**\n\n"
    detailed_text += "🚧 В разработке...\n\n"
    detailed_text += "Планируется добавить:\n"
    detailed_text += "• График активности по дням\n"
    detailed_text += "• Топ активных пользователей\n"
    detailed_text += "• Статистика по времени\n"
    detailed_text += "• Конверсия отзывов\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к статистике", callback_data="refresh_stats")]
    ])
    
    await callback.message.edit_text(detailed_text, parse_mode="Markdown", reply_markup=kb)
    await callback.answer()
