"""
Layer 1 — Ingestion
Collects raw Reddit posts from target subreddits.
Filters by time window and minimum engagement.
"""
import asyncio
import time
from typing import List
import asyncpraw

from app.config import get_settings
from app.database.models import RawPost
from app.database.connection import get_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

TRUSTED_SUBREDDITS = {
    "worldnews", "news", "geopolitics", "europe", "asia",
    "MiddleEast", "worldpolitics", "UkraineWarVideoReport",
    "russia", "china", "india", "africa",
}


def _engagement_score(score: int, comments: int) -> float:
    return round((score * 0.6) + (comments * 0.4), 2)


def _velocity_score(created_utc: float, score: int) -> float:
    """Posts per hour since creation — normalised."""
    age_hours = max((time.time() - created_utc) / 3600, 0.1)
    return round(score / age_hours, 2)


def get_existing_posts_for_today() -> List[RawPost]:
    """Check if any posts exist in the database for the current date."""
    conn = get_connection()
    # Check if there are any posts for the current UTC date
    res = conn.execute("SELECT * FROM raw_posts WHERE run_date = CURRENT_DATE").fetchall()
    if not res:
        return []
    
    posts = []
    # DuckDB columns based on schema in connection.py
    # id (0), title (1), subreddit (2), score (3), num_comments (4), created_utc (5), 
    # author (6), url (7), engagement_score (8), velocity_score (9)
    for r in res:
        posts.append(RawPost(
            id=r[0], title=r[1], subreddit=r[2], score=r[3], num_comments=r[4],
            created_utc=r[5], author=r[6], url=r[7] if r[7] else "", 
            engagement_score=r[8], velocity_score=r[9]
        ))
    return posts


async def fetch_reddit_posts() -> List[RawPost]:
    """Fetch posts from all configured subreddits asynchronously."""
    posts: List[RawPost] = []
    seen_ids: set = set()
    cutoff_utc = time.time() - (settings.REDDIT_TIME_WINDOW_HOURS * 3600)

    reddit = asyncpraw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )

    try:
        for sub_name in settings.subreddit_list:
            try:
                logger.info(f"Scanning r/{sub_name} ...")
                subreddit = await reddit.subreddit(sub_name)

                async for post in subreddit.hot(limit=settings.REDDIT_POST_LIMIT):
                    if post.id in seen_ids:
                        continue
                    if post.created_utc < cutoff_utc:
                        continue

                    eng = _engagement_score(post.score, post.num_comments)
                    if eng < settings.MIN_ENGAGEMENT_SCORE:
                        continue

                    raw = RawPost(
                        id=post.id,
                        title=post.title,
                        subreddit=sub_name,
                        score=post.score,
                        num_comments=post.num_comments,
                        created_utc=post.created_utc,
                        author=post.author.name if post.author else "[deleted]",
                        url=f"https://reddit.com{post.permalink}",
                        engagement_score=eng,
                        velocity_score=_velocity_score(post.created_utc, post.score),
                    )
                    posts.append(raw)
                    seen_ids.add(post.id)

            except Exception as e:
                logger.warning(f"Error fetching r/{sub_name}: {e}")
                continue

        await asyncio.sleep(0.5)

    finally:
        await reddit.close()

    logger.info(f"Ingestion complete — {len(posts)} posts collected")
    return posts


def persist_raw_posts(posts: List[RawPost]) -> None:
    """Upsert raw posts into DuckDB."""
    conn = get_connection()
    for p in posts:
        conn.execute("""
            INSERT OR REPLACE INTO raw_posts
            (id, title, subreddit, score, num_comments, created_utc,
             author, url, engagement_score, velocity_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [p.id, p.title, p.subreddit, p.score, p.num_comments,
              p.created_utc, p.author, p.url, p.engagement_score, p.velocity_score])
    logger.debug(f"Persisted {len(posts)} raw posts")


