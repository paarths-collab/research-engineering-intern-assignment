import duckdb
con = duckdb.connect('data/analysis_v2.db')
r1 = con.execute("SELECT COUNT(*) FROM posts WHERE url LIKE '%breitbart%'").fetchall()
r2 = con.execute("SELECT MIN(created_datetime), MAX(created_datetime) FROM posts").fetchall()
r3 = con.execute("SELECT subreddit, COUNT(*) as cnt FROM posts GROUP BY subreddit ORDER BY cnt DESC").fetchdf()
print("Breitbart count:", r1)
print("Date range:", r2)
print("Subreddits:\n", r3.to_string())
