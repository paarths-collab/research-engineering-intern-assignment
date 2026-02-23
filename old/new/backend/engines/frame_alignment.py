import os
import sys
import numpy as np
import chromadb
from sentence_transformers import SentenceTransformer

# Add root directory to sys.path for architecture imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database

# -----------------------------
# FRAME DEFINITIONS (EXPLICIT)
# -----------------------------

EXISTENTIAL_THREAT_ANCHORS = [
    "trump seeks autocratic power",
    "they are consolidating power under donald trump",
    "you cant wait out the trump administration",
    "he will take everything he can",
    "people must fight now or fight later",
    "trump is going to cause another civil war",
    "they are tearing down barriers to amass power",
    "antifascist circles call trump fascist",
    "mass protests against trump deportations",
    "trump concentration camps",
    "another authoritarian term",
    "maga authoritarian project",
    "you have to stop him",
    "doing nothing helps trump",
    "inaction strengthens fascism",
    "fight now before he gets stronger",
    "people must resist immediately",
    "waiting empowers the administration"
]

STRUCTURAL_CRITIQUE_ANCHORS = [
    "i do not vote because i believe it to be amoral",
    "elections are a trap",
    "showing up legitimizes it",
    "electoralism won’t fix anything",
    "voting changes nothing structurally",
    "the state responds to uprisings with repression",
    "the state itself pushes its narrative",
    "absence of anti-state presence",
    "institutionalized systems of abuse",
    "the system radicalizes people through violence",
    "corporate capitalism and techno-feudalism",
    "power structures within capitalism and colonialism",
    "not about individuals but systems",
    "prevent formation of a new state system",
    "focusing on trump misses deeper structures",
    "calling everything fascism hides real dynamics",
    "antifascism rhetoric can be misleading",
    "liberal framing obscures capitalism"
]

# -----------------------------
# COSINE SIMILARITY
# -----------------------------

def cosine_similarity(a, b):
    # Ensure inputs are numpy arrays
    a = np.asarray(a)
    b = np.asarray(b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return np.dot(a, b) / (norm_a * norm_b)


# -----------------------------
# MAIN ENGINE
# -----------------------------

def run_frame_alignment():
    print(f"Loading embedding model: {config.EMBEDDING_MODEL}...")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    print("Generating anchor embeddings...")
    existential_anchor_vecs = model.encode(EXISTENTIAL_THREAT_ANCHORS)
    structural_anchor_vecs = model.encode(STRUCTURAL_CRITIQUE_ANCHORS)

    print(f"Connecting to Chroma at {config.CHROMA_PATH}...")
    client = chromadb.PersistentClient(path=config.CHROMA_PATH)
    collection = client.get_collection(config.CHROMA_COLLECTION)

    print("Connecting to DuckDB...")
    con = database.get_connection()

    # Ensure columns exist in DuckDB
    existing_cols = con.execute("PRAGMA table_info('posts')").fetchdf()['name'].tolist()
    for col in ["fas_existential", "fas_structural"]:
        if col not in existing_cols:
            print(f"Adding column {col} to posts table...")
            con.execute(f"ALTER TABLE posts ADD COLUMN {col} DOUBLE")

    df = con.execute(f"""
        SELECT id
        FROM posts
        WHERE dataset = '{config.DATASET_NAME}'
    """).fetchdf()

    print(f"Computing FAS for {len(df)} posts...")

    for post_id in df["id"]:
        # Fetch embedding from Chroma
        result = collection.get(ids=[str(post_id)], include=["embeddings"])

        if result is None or "embeddings" not in result:
            continue

        if result["embeddings"] is None or len(result["embeddings"]) == 0:
            continue

        post_embedding = np.array(result["embeddings"][0])

        # Compute FAS scores (Max similarity across all anchors)
        fas_existential = max(
            cosine_similarity(post_embedding, anchor)
            for anchor in existential_anchor_vecs
        )

        fas_structural = max(
            cosine_similarity(post_embedding, anchor)
            for anchor in structural_anchor_vecs
        )

        # Store in DuckDB
        con.execute("""
            UPDATE posts
            SET fas_existential = ?,
                fas_structural = ?
            WHERE id = ?
        """, [float(fas_existential), float(fas_structural), post_id])


    con.close()
    print("Frame Alignment computation complete.")


if __name__ == "__main__":
    run_frame_alignment()
