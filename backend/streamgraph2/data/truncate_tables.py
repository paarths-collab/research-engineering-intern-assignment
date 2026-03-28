import asyncio
from streamgraph2.logic import db

async def main():
    await db.init_pool()

    async with db.conn() as conn:
        # Disable FK checks temporarily if needed
        await conn.execute("TRUNCATE TABLE posts RESTART IDENTITY CASCADE;")
        await conn.execute("TRUNCATE TABLE daily_volume RESTART IDENTITY CASCADE;")

        print("✓ Tables truncated successfully.")

    await db.close_pool()

asyncio.run(main())
