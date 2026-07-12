import asyncio
import sys
import os

sys.path.insert(0, "/app")

from src.database import get_async_session_maker
from sqlalchemy import text

async def main():
    session_maker = get_async_session_maker()
    async with session_maker() as db:
        result = await db.execute(text("SELECT id, title, domain FROM papers"))
        rows = result.all()
        print(f"Total papers in database: {len(rows)}")
        for r in rows:
            print(f"- ID: {r.id} | Domain: {r.domain} | Title: {r.title}")

if __name__ == "__main__":
    asyncio.run(main())
