import os
import sqlite3

db_path = r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\data\analysis_v2.db"

print("Working directory:", os.getcwd())
print("DB exists:", os.path.exists(db_path))
print("DB size:", os.path.getsize(db_path), "bytes")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("Tables:", tables)

conn.close()