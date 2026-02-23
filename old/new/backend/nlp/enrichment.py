import os
import sys
import duckdb
import spacy
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import database

print(f"Loading spaCy model: {config.SPACY_MODEL}...")
try:
    nlp = spacy.load(config.SPACY_MODEL)
except:
    print(f"Model {config.SPACY_MODEL} not found. Falling back to en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")

GENERIC_WORDS = {
    "week", "thing", "subject", "club", "purpose",
    "tweet", "time", "way", "year", "people"
}

def extract_svo(doc):
    subject = ""
    verb = ""
    obj = ""

    # Prefer Named Entities as subjects
    for ent in doc.ents:
        if ent.label_ in ["PERSON", "ORG", "GPE"]:
            subject = ent.text
            break

    # If no entity found, fallback to noun subject
    if not subject:
        for token in doc:
            if token.dep_ == "nsubj" and token.pos_ in ["PROPN", "NOUN"]:
                if token.text.lower() not in GENERIC_WORDS:
                    subject = token.text
                    break

    # Verb
    for token in doc:
        if token.pos_ == "VERB":
            verb = token.lemma_
            break

    # Object
    for token in doc:
        if token.dep_ in ["dobj", "pobj"] and token.pos_ in ["PROPN", "NOUN"]:
            if token.text.lower() not in GENERIC_WORDS:
                obj = token.text
                break

    return subject, verb, obj

def run_enrichment():
    conn = database.get_connection()

    # Check/Add columns
    existing_cols = conn.execute("PRAGMA table_info('posts')").fetchdf()['name'].tolist()
    for col in ["lemmatized_text", "entities", "subject", "verb", "object"]:
        if col not in existing_cols:
            print(f"Adding column {col} to posts table...")
            conn.execute(f"ALTER TABLE posts ADD COLUMN {col} TEXT")

    df = conn.execute(f"""
        SELECT id, clean_text
        FROM posts
        WHERE dataset = '{config.DATASET_NAME}'
    """).fetchdf()

    print(f"Processing {len(df)} posts for enrichment...")

    for i in tqdm(range(len(df))):
        text = df.iloc[i]["clean_text"]
        doc = nlp(text)

        # Lemmatization (no stopwords)
        lemmatized = " ".join([token.lemma_ for token in doc if not token.is_stop])

        # Named Entities
        entities = str([(ent.text, ent.label_) for ent in doc.ents])

        # SVO extraction
        subject, verb, obj = extract_svo(doc)

        conn.execute("""
            UPDATE posts
            SET lemmatized_text = ?,
                entities = ?,
                subject = ?,
                verb = ?,
                object = ?
            WHERE id = ?
        """, [
            lemmatized,
            entities,
            subject,
            verb,
            obj,
            df.iloc[i]["id"]
        ])

    conn.close()
    print("NLP enrichment complete.")

if __name__ == "__main__":
    run_enrichment()
