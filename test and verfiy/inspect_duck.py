import duckdb

db_path = r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\data\analysis_v2.db"

con = duckdb.connect(db_path)

tables = con.execute("SHOW TABLES").fetchall()

for table in tables:
    table_name = table[0]
    print(f"\nSchema for {table_name}:")
    print(con.execute(f"DESCRIBE {table_name}").fetchall())

con.close()