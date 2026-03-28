import asyncio
from streamgraph2.logic import db

async def clear():
    await db.init_pool()
    async with db.conn() as c:
        await c.execute('DELETE FROM posts')
        await c.execute('DELETE FROM daily_volume')
        await c.execute('DELETE FROM comments')
        await c.execute('DELETE FROM topic_results')
        await c.execute('DELETE FROM spike_jobs')
    await db.close_pool()
    print("Database cleared.")

asyncio.run(clear())
