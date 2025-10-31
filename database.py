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
            status TEXT NOT NULL DEFAULT 'pending'
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS message_templates (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            text TEXT NOT NULL
        );
    """)
    await conn.close()

# --- USERS ---
async def add_or_update_user(user_id, username, first_name, last_name):
    conn = await get_connection()
    await conn.execute(
        """
        INSERT INTO users (user_id, username, first_name, last_name)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name
        """,
        user_id, username, first_name, last_name
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