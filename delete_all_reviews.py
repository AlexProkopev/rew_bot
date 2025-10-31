import asyncio
import database

async def main():
    conn = await database.get_connection()
    await conn.execute("DELETE FROM reviews")
    await conn.close()
    print("Все отзывы удалены.")

if __name__ == "__main__":
    asyncio.run(main())
