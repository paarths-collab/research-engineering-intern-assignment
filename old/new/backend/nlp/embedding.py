import os
import sys
import duckdb
from sentence_transformers import SentenceTransformer
import chromadb
from tqdm import tqdm
import pandas as pd

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database

def run_embeddings():
    print("Loading posts from DuckDB...")
    conn = database.get_connection()

    df = conn.execute(f"""
        SELECT id, clean_text, author, subreddit, timestamp
        FROM posts
        WHERE dataset = '{config.DATASET_NAME}'
    """).fetchdf()

    conn.close()

    print(f"Loaded {len(df)} posts.")

    if df.empty:
        print("No data found.")
        return

    print(f"Loading embedding model: {config.EMBEDDING_MODEL}...")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    print("Generating embeddings...")
    embeddings = model.encode(
        df["clean_text"].tolist(),
        batch_size=32,
        show_progress_bar=True
    )

    print(f"Connecting to ChromaDB at {config.CHROMA_PATH}...")
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)

    collection_name = f"{config.DATASET_NAME}_collection"
    collection = client.get_or_create_collection(name=collection_name)

    print(f"Inserting {len(df)} vectors into ChromaDB collection '{collection_name}'...")
    
    # Process in batches for ChromaDB efficiency
    batch_size = 100
    for i in tqdm(range(0, len(df), batch_size)):
        end = min(i + batch_size, len(df))
        batch_df = df.iloc[i:end]
        batch_embeddings = embeddings[i:end].tolist()
        
        collection.add(
            ids=[str(val) for val in batch_df["id"].tolist()],
            documents=batch_df["clean_text"].tolist(),
            embeddings=batch_embeddings,
            metadatas=[{
                "dataset": config.DATASET_NAME,
                "author": row["author"],
                "subreddit": row["subreddit"],
                "timestamp": str(row["timestamp"])
            } for _, row in batch_df.iterrows()]
        )

    print("Embedding phase complete. Vectors stored successfully.")

if __name__ == "__main__":
    run_embeddings()
