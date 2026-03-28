import csv
from datetime import datetime

def parse_ts(val: str) -> datetime:
    for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(val.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse timestamp: {val!r}")

path = r"C:\Users\Paarth\Coding\simppl\research-engineering-intern-assignment\data\clean_posts.csv"

with open(path, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    dates = []
    for i, row in enumerate(reader):
        dt = parse_ts(row["created_datetime"])
        dates.append(dt)
        if i < 5:
            print("Sample:", dt)

print("\nMin:", min(dates))
print("Max:", max(dates))
print("Total rows checked:", len(dates))