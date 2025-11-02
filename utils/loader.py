# telegram_reviews_bot/utils/loader.py
import asyncio
from aiogram.types import Message, CallbackQuery
from aiogram import Bot

class LoadingAnimation:
    """Класс для создания анимированных лоадеров."""
    
    def __init__(self, message: Message, initial_text: str = "Загрузка..."):
        self.message = message
        self.initial_text = initial_text
        self.is_running = False
        self.animation_task = None
    
    async def start(self):
        """Запускает анимацию загрузки."""
        if self.is_running:
            return
        
        self.is_running = True
        self.animation_task = asyncio.create_task(self._animate())
    
    async def stop(self, final_text: str = None):
        """Останавливает анимацию."""
        self.is_running = False
        if self.animation_task:
            self.animation_task.cancel()
            try:
                await self.animation_task
            except asyncio.CancelledError:
                pass
        
        if final_text:
            try:
                await self.message.edit_text(final_text)
            except:
                pass
    
    async def _animate(self):
        """Анимация с вращающимися эмодзи."""
        frames = ["🔄", "🔃", "🔄", "🔃"]
        dots = ["", ".", "..", "..."]
        
        frame_idx = 0
        dot_idx = 0
        
        while self.is_running:
            try:
                current_frame = frames[frame_idx % len(frames)]
                current_dots = dots[dot_idx % len(dots)]
                
                text = f"{current_frame} {self.initial_text}{current_dots}"
                await self.message.edit_text(text)
                
                frame_idx += 1
                if frame_idx % 2 == 0:  # Меняем точки медленнее
                    dot_idx += 1
                
                await asyncio.sleep(0.5)
                
            except Exception:
                break

class CallbackLoadingAnimation:
    """Класс для лоадеров в callback запросах."""
    
    def __init__(self, callback: CallbackQuery, initial_text: str = "Загрузка..."):
        self.callback = callback
        self.message = callback.message
        self.initial_text = initial_text
        self.is_running = False
        self.animation_task = None
    
    async def start(self):
        """Запускает анимацию загрузки."""
        if self.is_running:
            return
        
        self.is_running = True
        # Сразу показываем первый кадр
        await self.message.edit_text(f"🔄 {self.initial_text}")
        self.animation_task = asyncio.create_task(self._animate())
    
    async def stop(self, final_text: str = None, reply_markup=None):
        """Останавливает анимацию."""
        self.is_running = False
        if self.animation_task:
            self.animation_task.cancel()
            try:
                await self.animation_task
            except asyncio.CancelledError:
                pass
        
        if final_text:
            try:
                if reply_markup:
                    await self.message.edit_text(final_text, reply_markup=reply_markup)
                else:
                    await self.message.edit_text(final_text)
            except:
                pass
    
    async def _animate(self):
        """Анимация с различными эмодзи."""
        frames = ["🔄", "⏳", "🔄", "⌛"]
        dots = ["", ".", "..", "..."]
        
        frame_idx = 0
        dot_idx = 0
        
        while self.is_running:
            try:
                current_frame = frames[frame_idx % len(frames)]
                current_dots = dots[dot_idx % len(dots)]
                
                text = f"{current_frame} {self.initial_text}{current_dots}"
                await self.message.edit_text(text)
                
                frame_idx += 1
                if frame_idx % 2 == 0:
                    dot_idx += 1
                
                await asyncio.sleep(0.6)
                
            except Exception:
                break

# Готовые лоадеры для разных операций
async def loading_reviews(callback: CallbackQuery):
    """Лоадер для загрузки отзывов."""
    loader = CallbackLoadingAnimation(callback, "Загружаем отзывы")
    await loader.start()
    return loader

async def loading_statistics(callback: CallbackQuery):
    """Лоадер для загрузки статистики."""
    loader = CallbackLoadingAnimation(callback, "Собираем статистику")
    await loader.start()
    return loader

async def loading_photo(callback: CallbackQuery):
    """Лоадер для загрузки фото."""
    loader = CallbackLoadingAnimation(callback, "Загружаем фото")
    await loader.start()
    return loader

async def loading_latest_reviews(callback: CallbackQuery):
    """Лоадер для загрузки последних отзывов."""
    loader = CallbackLoadingAnimation(callback, "Готовим последние отзывы")
    await loader.start()
    return loader

async def loading_user_data(callback: CallbackQuery):
    """Лоадер для загрузки данных пользователей."""
    loader = CallbackLoadingAnimation(callback, "Загружаем пользователей")
    await loader.start()
    return loader

async def loading_photo_upload(message: Message):
    """Лоадер для загрузки фото (для обычных сообщений)."""
    loader = LoadingAnimation(message, "Обрабатываем фото и отправляем отзыв")
    await loader.start()
    return loader

class MailingProgressLoader:
    """Специальный лоадер для рассылки с прогрессом."""
    
    def __init__(self, message: Message, total_users: int):
        self.message = message
        self.total_users = total_users
        self.sent_count = 0
        self.failed_count = 0
        self.is_running = True
    
    async def update_progress(self, sent: int, failed: int):
        """Обновляет прогресс рассылки."""
        self.sent_count = sent
        self.failed_count = failed
        
        if not self.is_running:
            return
            
        progress = (sent + failed) / self.total_users * 100
        progress_bar = "█" * int(progress // 5) + "░" * (20 - int(progress // 5))
        
        text = f"📡 **Идет рассылка...**\n\n"
        text += f"Прогресс: {progress:.1f}% [{progress_bar}]\n\n"
        text += f"✅ Отправлено: {sent}\n"
        text += f"❌ Не удалось: {failed}\n"
        text += f"📊 Всего пользователей: {self.total_users}"
        
        try:
            await self.message.edit_text(text, parse_mode="Markdown")
        except:
            pass
    
    async def finish(self):
        """Завершает рассылку."""
        self.is_running = False
        
        text = f"✅ **Рассылка завершена!**\n\n"
        text += f"📤 Отправлено: {self.sent_count}\n"
        text += f"❌ Не удалось отправить: {self.failed_count}\n"
        text += f"📊 Всего пользователей: {self.total_users}\n\n"
        
        success_rate = (self.sent_count / self.total_users * 100) if self.total_users > 0 else 0
        text += f"📈 Успешность: {success_rate:.1f}%"
        
        try:
            await self.message.edit_text(text, parse_mode="Markdown")
        except:
            pass