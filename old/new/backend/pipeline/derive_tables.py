import pandas as pd
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_PATH = BASE_DIR / "data" / "derived" / "semantic_points.parquet"
DERIVED_DIR = BASE_DIR / "data" / "derived"

df = pd.read_parquet(INPUT_PATH)

df.rename(columns={"timestamp": "created", "week": "week_bucket"}, inplace=True)
if "phrase_hits" not in df.columns:
    df["phrase_hits"] = [[] for _ in range(len(df))]

# -------------------------------------------------
# 1️⃣ WEEKLY COUNTS (SEISMOGRAPH)
# -------------------------------------------------

weekly_counts = (
    df.groupby(["week_bucket", "cluster_label"])
      .size()
      .reset_index(name="post_count")
)

weekly_counts.to_parquet(DERIVED_DIR / "weekly_counts.parquet", index=False)


# -------------------------------------------------
# 2️⃣ AUTHOR ALIGNMENT (ALLEGIANCE MAP)
# -------------------------------------------------

author_cluster_counts = (
    df.groupby(["author", "cluster_label"])
      .size()
      .reset_index(name="post_count")
)

total_posts_per_author = (
    df.groupby("author")
      .size()
      .reset_index(name="total_posts")
)

author_alignment = author_cluster_counts.merge(
    total_posts_per_author,
    on="author"
)

author_alignment["alignment_ratio"] = (
    author_alignment["post_count"] /
    author_alignment["total_posts"]
)

author_alignment.to_parquet(
    DERIVED_DIR / "author_alignment.parquet",
    index=False
)


# -------------------------------------------------
# 3️⃣ CONFLICT PAIR FLAG (48 HOUR WINDOW)
# -------------------------------------------------

df_sorted = df.sort_values("created")
df_sorted["conflict_pair_flag"] = False

for i in range(len(df_sorted)):
    current_row = df_sorted.iloc[i]
    current_time = current_row["created"]
    current_cluster = current_row["cluster_label"]

    window = df_sorted[
        (df_sorted["created"] > current_time) &
        (df_sorted["created"] <= current_time + timedelta(hours=48)) &
        (df_sorted["cluster_label"] != current_cluster)
    ]

    if not window.empty:
        df_sorted.at[df_sorted.index[i], "conflict_pair_flag"] = True

conflict_density = (
    df_sorted.groupby(["week_bucket", "cluster_label"])["conflict_pair_flag"]
    .sum()
    .reset_index(name="conflict_count")
)

conflict_density.to_parquet(
    DERIVED_DIR / "conflict_density.parquet",
    index=False
)


# -------------------------------------------------
# 4️⃣ PHRASE TIMELINE (PHRASE CASCADE)
# -------------------------------------------------

phrase_rows = []

for idx, row in df.iterrows():
    for phrase in row["phrase_hits"]:
        phrase_rows.append({
            "phrase": phrase,
            "created": row["created"],
            "author": row["author"],
            "cluster_label": row["cluster_label"]
        })

phrase_timeline = pd.DataFrame(phrase_rows)

phrase_timeline.to_parquet(
    DERIVED_DIR / "phrase_timeline.parquet",
    index=False
)


# -------------------------------------------------
# 5️⃣ AUTHOR PERIOD COHORTS (BIFURCATION)
# -------------------------------------------------

df["period"] = pd.cut(
    df["created"],
    bins=5,
    labels=["P1", "P2", "P3", "P4", "P5"]
)

author_period = (
    df.groupby(["author", "period", "cluster_label"])
      .size()
      .reset_index(name="post_count")
)

author_period.to_parquet(
    DERIVED_DIR / "author_period_cohorts.parquet",
    index=False
)

print("All derived tables generated.")