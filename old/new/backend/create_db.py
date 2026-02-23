import duckdb

DB_NAME = "social_lab.duckdb"

con = duckdb.connect(DB_NAME)

con.execute("""
CREATE TABLE IF NOT EXISTS posts (
    id TEXT,
    dataset TEXT,
    author TEXT,
    subreddit TEXT,
    timestamp TIMESTAMP,
    date DATE,
    week DATE,
    clean_text TEXT,
    score INTEGER,
    upvote_ratio DOUBLE
);
""")

print("Database and posts table created.")

con.close()
