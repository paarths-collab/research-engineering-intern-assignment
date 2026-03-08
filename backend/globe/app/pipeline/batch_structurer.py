import json
import re
import asyncio
import hashlib
from typing import List, Optional, Dict, Tuple
from langchain_groq import ChatGroq

from app.config import get_settings
from app.database.models import RawPost, StructuredEvent, ResolvedLocation
from app.database.connection import get_connection
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

def _get_llm() -> ChatGroq:
    return ChatGroq(
        api_key=settings.GROQ_API_KEY,
        model=settings.FAST_MODEL,
        temperature=0,
        max_retries=3,
        max_tokens=1024, # small budget
    )

def _normalize_text(text: str) -> str:
    """Strategy 4: Normalize tokens for caching."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    stopwords = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with"}
    tokens = [t for t in text.split() if t not in stopwords]
    tokens.sort()
    return " ".join(tokens)

def _hash_text(text: str) -> str:
    """Strategy 3: Hash the normalized text."""
    return hashlib.md5(_normalize_text(text).encode('utf-8')).hexdigest()

def _get_cached_event(post_hash: str) -> Optional[StructuredEvent]:
    conn = get_connection()
    # Wait, the DB doesn't store post_hash yet. We need to add it or use post_id.
    # Actually, we can check by post_id first. Or we can just add a new table/column.
    # To not break the schema, we can match by title hash if we persist it, or just use a local dict cache for the run, or DuckDB.
    # Let's add `text_hash` to structured_events if possible, or just query all existing structured_events into a memory map.
    return None # implemented below

# Memory Cache for this run
_geo_cache: Dict[str, StructuredEvent] = {}

def load_cache():
    conn = get_connection()
    rows = conn.execute(
        """SELECT e.id, e.post_id, e.event_type, e.primary_location,
                  e.secondary_locations, e.key_entities, e.search_queries, p.title
           FROM structured_events e
           JOIN raw_posts p ON e.post_id = p.id"""
    ).fetchall()
    
    for row in rows:
        title = row[7]
        if not title: continue
        thash = _hash_text(title)
        _geo_cache[thash] = StructuredEvent(
            id=row[0], post_id=row[1], event_type=row[2],
            primary_location=row[3],
            secondary_locations=json.loads(row[4] or "[]"),
            key_entities=json.loads(row[5] or "[]"),
            search_queries=json.loads(row[6] or "[]"),
        )
    logger.info(f"Loaded {len(_geo_cache)} cached structured events by hash.")

async def process_batch(posts: List[RawPost], llm: ChatGroq) -> List[StructuredEvent]:
    if not posts: return []
    
    prompt = "Analyze the following geopolitical news headlines.\n"
    prompt += "Extract the PRIMARY physical location, event_type, secondary_locations, key_entities, search_queries, and a geo_confidence score (0.0 to 1.0).\n"
    prompt += "Return EXACTLY a JSON array of objects, each containing: 'post_index' (int), 'primary_location' (string or null), 'event_type' (string), 'secondary_locations' (list), 'key_entities' (list), 'search_queries' (list of 3 strings), 'geo_confidence' (float).\n\n"
    
    for i, p in enumerate(posts):
        prompt += f"Headline {i}: {p.title}\n"
        
    for attempt in range(3):
        try:
            msg = await llm.ainvoke(prompt)
            content = msg.content
            
            # extract json array
            match = re.search(r'\[.*\]', content, re.DOTALL)
            if not match:
                logger.warning(f"Failed to find JSON array in batch response.")
                return []
                
            data = json.loads(match.group(0))
            
            results = []
            for item in data:
                idx = item.get("post_index")
                if idx is None or not isinstance(idx, int) or idx >= len(posts):
                    continue
                
                # Strategy 7: Confidence Threshold    
                conf = item.get("geo_confidence", 0.0)
                if conf < 0.5:
                    continue
                    
                loc = item.get("primary_location")
                if not loc or loc.lower() in ["unknown", "none", "null"]:
                    continue
                    
                post = posts[idx]
                se = StructuredEvent(
                    id=f"evt_{post.id}",
                    post_id=post.id,
                    event_type=item.get("event_type", "unknown"),
                    primary_location=loc,
                    secondary_locations=item.get("secondary_locations", []),
                    key_entities=item.get("key_entities", []),
                    search_queries=item.get("search_queries", [])
                )
                results.append(se)
                
            return results
                
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                match = re.search(r"try again in (\d+(?:\.\d+)?)s", err)
                wait = float(match.group(1)) + 2 if match else 15 * (attempt + 1)
                logger.warning(f"Rate limit on batch structurer, waiting {wait:.1f}s (attempt {attempt+1}/3)")
                await asyncio.sleep(wait)
            else:
                logger.warning(f"Batch parse error: {e}")
                break
                
    return []

async def batch_structure_posts(posts: List[RawPost]) -> List[StructuredEvent]:
    load_cache()
    llm = _get_llm()
    
    final_events = []
    to_process = []
    
    for p in posts:
        thash = _hash_text(p.title)
        if thash in _geo_cache:
            # Clone cached structure with new post id
            cached = _geo_cache[thash]
            final_events.append(StructuredEvent(
                id=f"evt_{p.id}",
                post_id=p.id,
                event_type=cached.event_type,
                primary_location=cached.primary_location,
                secondary_locations=cached.secondary_locations,
                key_entities=cached.key_entities,
                search_queries=cached.search_queries
            ))
        else:
            to_process.append(p)
            
    logger.info(f"Batch structurer: {len(posts)-len(to_process)} from cache, {len(to_process)} to LLM.")
            
    # Batch in sizes of 8 (Strategy 1)
    batch_size = 8
    
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i:i+batch_size]
        await asyncio.sleep(3) # safe delay
        results = await process_batch(batch, llm)
        final_events.extend(results)
        
    logger.info(f"Batch execution complete. Extracted {len(final_events)} structured events.")
    _persist_structured_events(final_events)
    return final_events

def _persist_structured_events(events: List[StructuredEvent]) -> None:
    conn = get_connection()
    for e in events:
        conn.execute("""
            INSERT OR REPLACE INTO structured_events
            (id, post_id, event_type, primary_location, secondary_locations, key_entities, search_queries)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [e.id, e.post_id, e.event_type, e.primary_location,
              json.dumps(e.secondary_locations), json.dumps(e.key_entities),
              json.dumps(e.search_queries)])
