#!/usr/bin/env python3
# Test all loaders animations
import asyncio
from utils.loader import LoadingAnimation, CallbackLoadingAnimation

class MockMessage:
    """Мок-объект для тестирования."""
    def __init__(self, name):
        self.name = name
        self.text = ""
    
    async def edit_text(self, text, **kwargs):
        print(f"[{self.name}]: {text}")
        self.text = text

class MockCallback:
    """Мок callback для тестирования."""
    def __init__(self, name):
        self.message = MockMessage(name)

async def test_all_loaders():
    """Сравнение всех лоадеров."""
    print("🎭 ТЕСТ ВСЕХ ЛОАДЕРОВ\n")
    
    # Тест LoadingAnimation (для обычных сообщений)
    print("1️⃣ LoadingAnimation (для команды 'Показать отзывы'):")
    print("-" * 50)
    mock_msg = MockMessage("LoadingAnimation")
    loader1 = LoadingAnimation(mock_msg, "📄 Загружаем отзывы")
    await loader1.start()
    await asyncio.sleep(2)
    await loader1.stop("✅ Отзывы загружены!")
    
    print("\n")
    
    # Тест CallbackLoadingAnimation (для кнопок)  
    print("2️⃣ CallbackLoadingAnimation (для кнопок пагинации):")
    print("-" * 50)
    mock_callback = MockCallback("CallbackLoadingAnimation")
    loader2 = CallbackLoadingAnimation(mock_callback, "📄 Загружаем отзывы")
    await loader2.start()
    await asyncio.sleep(2)
    await loader2.stop("Отзывы показаны")
    
    print("\n")
    
    # Тест разных типов лоадеров
    loaders_to_test = [
        ("📊 Статистика", "📊 Собираем статистику"),
        ("🖼️ Фото", "🖼️ Загружаем фото"), 
        ("🌟 Топ-5", "🌟 Готовим последние отзывы"),
        ("👥 Пользователи", "👥 Загружаем пользователей")
    ]
    
    print("3️⃣ Разные типы callback лоадеров:")
    print("-" * 50)
    
    for name, text in loaders_to_test:
        print(f"\n🔹 {name}:")
        mock_cb = MockCallback(name)
        loader = CallbackLoadingAnimation(mock_cb, text)
        await loader.start()
        await asyncio.sleep(1.5)
        await loader.stop("Готово!")
        
    print("\n✅ Тест завершен! Теперь все лоадеры одинаково заметны.")

if __name__ == "__main__":
    asyncio.run(test_all_loaders())