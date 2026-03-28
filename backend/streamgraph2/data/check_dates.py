import asyncio
from streamgraph2.logic import db

async def main():
    await db.init_pool()

    async with db.conn() as c:
        rows = await c.fetch("""
            SELECT DATE(created_utc) AS d,
                   COUNT(*) AS c
            FROM posts
            GROUP BY d
            ORDER BY d DESC
            LIMIT 10;
        """)

        print([dict(r) for r in rows])

    await db.close_pool()

asyncio.run(main())
