import duckdb
from config import DB_NAME

def get_connection():
    return duckdb.connect(DB_NAME)
