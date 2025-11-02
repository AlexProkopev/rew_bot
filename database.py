# --- УДАЛЕНИЕ ОТЗЫВА ---
async def delete_review(review_id):
    conn = await get_connection()
    await conn.execute("DELETE FROM reviews WHERE id = $1", review_id)
    await conn.close()
# telegram_reviews_bot/database.py

import asyncpg
from config import DATABASE_URL

async def get_connection():
    return await asyncpg.connect(DATABASE_URL)

async def init_db():
    conn = await get_connection()
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            username TEXT,
            text TEXT NOT NULL,
            photo_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS message_templates (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            text TEXT NOT NULL
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_activity (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            action TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # Добавляем колонки в существующие таблицы, если их нет
    try:
        await conn.execute("ALTER TABLE reviews ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    except:
        pass
    
    await conn.close()

# --- USERS ---
async def add_or_update_user(user_id, username, first_name, last_name):
    conn = await get_connection()
    # Проверяем, новый ли это пользователь
    existing = await conn.fetchval("SELECT user_id FROM users WHERE user_id = $1", user_id)
    is_new_user = existing is None
    
    await conn.execute(
        """
        INSERT INTO users (user_id, username, first_name, last_name, last_activity)
        VALUES ($1, $2, $3, $4, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET 
            username=EXCLUDED.username, 
            first_name=EXCLUDED.first_name, 
            last_name=EXCLUDED.last_name,
            last_activity=CURRENT_TIMESTAMP
        """,
        user_id, username, first_name, last_name
    )
    
    # Логируем активность
    if is_new_user:
        await conn.execute(
            "INSERT INTO user_activity (user_id, action) VALUES ($1, $2)",
            user_id, "user_joined"
        )
    else:
        await conn.execute(
            "INSERT INTO user_activity (user_id, action) VALUES ($1, $2)",
            user_id, "user_activity"
        )
    
    await conn.close()

async def get_all_users(page=1, limit=10, search_query=None):
    offset = (page - 1) * limit
    conn = await get_connection()
    if search_query:
        users = await conn.fetch(
            """
            SELECT user_id, username, first_name FROM users
            WHERE username ILIKE $1 OR first_name ILIKE $1
            LIMIT $2 OFFSET $3
            """,
            f"%{search_query}%", limit, offset
        )
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE username ILIKE $1 OR first_name ILIKE $1",
            f"%{search_query}%"
        )
    else:
        users = await conn.fetch(
            "SELECT user_id, username, first_name FROM users LIMIT $1 OFFSET $2",
            limit, offset
        )
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
    await conn.close()
    return users, total

async def get_all_user_ids():
    conn = await get_connection()
    rows = await conn.fetch("SELECT user_id FROM users")
    await conn.close()
    return [row["user_id"] for row in rows]

# --- REVIEWS ---
async def add_review(user_id, username, text, photo_id=None):
    conn = await get_connection()
    row = await conn.fetchrow(
        """
        INSERT INTO reviews (user_id, username, text, photo_id)
        VALUES ($1, $2, $3, $4)
        RETURNING id
        """,
        user_id, username, text, photo_id
    )
    await conn.close()
    return row["id"]

async def get_review(review_id):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT * FROM reviews WHERE id = $1", review_id)
    await conn.close()
    return row

async def update_review_status(review_id, status):
    conn = await get_connection()
    await conn.execute("UPDATE reviews SET status = $1 WHERE id = $2", status, review_id)
    await conn.close()

async def get_approved_reviews(offset=0, limit=5):
    conn = await get_connection()
    rows = await conn.fetch(
        "SELECT * FROM reviews WHERE status = 'approved' ORDER BY id DESC LIMIT $1 OFFSET $2",
        limit, offset
    )
    await conn.close()
    return rows

async def count_approved_reviews():
    conn = await get_connection()
    count = await conn.fetchval("SELECT COUNT(*) FROM reviews WHERE status = 'approved'")
    await conn.close()
    return count

# --- TEMPLATES ---
async def add_template(name, text):
    conn = await get_connection()
    await conn.execute(
        """
        INSERT INTO message_templates (name, text)
        VALUES ($1, $2)
        ON CONFLICT (name) DO UPDATE SET text=EXCLUDED.text
        """,
        name, text
    )
    await conn.close()

async def get_template(name):
    conn = await get_connection()
    row = await conn.fetchrow("SELECT * FROM message_templates WHERE name = $1", name)
    await conn.close()
    return row

async def get_all_templates():
    conn = await get_connection()
    rows = await conn.fetch("SELECT name FROM message_templates")
    await conn.close()
    return rows

# --- СТАТИСТИКА ---
async def get_total_users_count():
    """Получить общее количество пользователей."""
    conn = await get_connection()
    count = await conn.fetchval("SELECT COUNT(*) FROM users")
    await conn.close()
    return count

async def get_total_reviews_count():
    """Получить общее количество отзывов."""
    conn = await get_connection()
    count = await conn.fetchval("SELECT COUNT(*) FROM reviews")
    await conn.close()
    return count

async def get_daily_new_users():
    """Получить количество новых пользователей за сегодня."""
    conn = await get_connection()
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM users WHERE DATE(created_at) = CURRENT_DATE"
    )
    await conn.close()
    return count

async def get_daily_reviews():
    """Получить количество отзывов за сегодня."""
    conn = await get_connection()
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM reviews WHERE DATE(created_at) = CURRENT_DATE"
    )
    await conn.close()
    return count

async def get_active_users_today():
    """Получить количество активных пользователей сегодня."""
    conn = await get_connection()
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM users WHERE DATE(last_activity) = CURRENT_DATE"
    )
    await conn.close()
    return count

async def get_inactive_users_count():
    """Получить количество неактивных пользователей (более 7 дней без активности)."""
    conn = await get_connection()
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM users WHERE last_activity < CURRENT_DATE - INTERVAL '7 days'"
    )
    await conn.close()
    return count

async def log_user_activity(user_id, action):
    """Записать активность пользователя."""
    conn = await get_connection()
    await conn.execute(
        "INSERT INTO user_activity (user_id, action) VALUES ($1, $2)",
        user_id, action
    )
    # Обновляем последнюю активность пользователя
    await conn.execute(
        "UPDATE users SET last_activity = CURRENT_TIMESTAMP WHERE user_id = $1",
        user_id
    )
    await conn.close()

async def get_reviews_by_status():
    """Получить статистику отзывов по статусам."""
    conn = await get_connection()
    stats = await conn.fetch(
        "SELECT status, COUNT(*) as count FROM reviews GROUP BY status"
    )
    await conn.close()
    return {row['status']: row['count'] for row in stats}