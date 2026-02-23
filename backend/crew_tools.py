import duckdb
import time
from backend.database import get_db_connection, semantic_search

# NO DECORATOR HERE
def execute_sql_func(sql_query: str):
    """
    Useful for quantitative questions (counts, averages, time-series, spikes).
    Input must be a valid DuckDB SQL SELECT query for table 'posts'.
    Columns: id, created_datetime, subreddit, author, title, domain, score, num_comments, duplicate_cluster_id
    Date filtering: use CAST(created_datetime AS DATE) = 'YYYY-MM-DD'
    """
    time.sleep(4)  # Prevent Groq rate limits (6000 RPM)
    conn = get_db_connection()
    try:
        clean_query = sql_query.replace("```sql", "").replace("```", "").strip()

        # Safety: only allow SELECT queries
        if not clean_query.lower().startswith("select"):
            return "Error: Only SELECT queries are allowed."

        df = conn.execute(clean_query).fetchdf()
        if df.empty:
            return "Query ran successfully but returned 0 results."
        return df.to_string()
    except Exception as e:
        return f"SQL Error: {str(e)}. Check that you used CAST(created_datetime AS DATE) for date filtering and only valid column names."

def search_vectors_func(topic: str):
    """
    Useful for qualitative questions (sentiment, framing, narrative, opinions).
    """
    time.sleep(4)  # Prevent Groq rate limits
    results = semantic_search(topic, top_k=5)
    response_str = ""
    for r in results:
        response_str += f"- [r/{r['subreddit']}] ({r['date']}): {r['title']}\n"
    return response_str

def analyze_bridges_func(subreddit_a: str, subreddit_b: str):
    """
    Useful for finding specific users who connect two communities.
    """
    time.sleep(4)  # Prevent Groq rate limits
    conn = get_db_connection()
    query = f"""
    SELECT author, count(*) as volume 
    FROM posts 
    WHERE subreddit IN ('{subreddit_a}', '{subreddit_b}')
    GROUP BY author 
    HAVING COUNT(DISTINCT subreddit) > 1
    ORDER BY volume DESC
    LIMIT 5
    """
    df = conn.execute(query).fetchdf()
    return df.to_string()