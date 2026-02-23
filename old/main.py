# ==============================
# COMPLETE TOPIC MODELING PIPELINE
# ==============================

import pandas as pd
import re
import nltk
import os
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.decomposition import LatentDirichletAllocation, NMF

# ------------------------------
# 1️⃣ Load Data
# ------------------------------
DATA_PATH = r"C:\Users\Paarth\Downloads\data.jsonl"
df = pd.read_json(DATA_PATH, lines=True)
df: pd.DataFrame = pd.json_normalize(df["data"]) # type: ignore
df["text"] = df["title"].fillna("") + " " + df["selftext"].fillna("") # type: ignore

print("Total posts:", len(df))

# ------------------------------
# 2️⃣ Preprocessing
# ------------------------------
try:
    stop_words = set(stopwords.words("english"))
except LookupError:
    stop_words = set(ENGLISH_STOP_WORDS)
    try:
        nltk.download("stopwords", quiet=True)
    except Exception:
        pass
    print("NLTK stopwords not found; using sklearn ENGLISH_STOP_WORDS fallback.")

try:
    lemmatizer = WordNetLemmatizer()
    _ = lemmatizer.lemmatize("tests")
except LookupError:
    lemmatizer = None
    try:
        nltk.download("wordnet", quiet=True)
    except Exception:
        pass
    print("NLTK wordnet not found; skipping lemmatization.")

def preprocess(text):
    text = text.lower()
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"[^a-z\s]", "", text)
    tokens = text.split()
    if lemmatizer is None:
        tokens = [word for word in tokens if word not in stop_words and len(word) > 2]
    else:
        tokens = [
            lemmatizer.lemmatize(word)
            for word in tokens
            if word not in stop_words and len(word) > 2
        ]
    return " ".join(tokens)

df["clean_text"] = df["text"].apply(preprocess)

# ------------------------------
# 3️⃣ LDA (Count-Based)
# ------------------------------
NUM_TOPICS = 5

count_vectorizer = CountVectorizer(max_df=0.9, min_df=5, ngram_range=(1,2))
X_counts = count_vectorizer.fit_transform(df["clean_text"])

lda = LatentDirichletAllocation(n_components=NUM_TOPICS, random_state=42)
lda.fit(X_counts)

df["lda_topic"] = lda.transform(X_counts).argmax(axis=1)

# ------------------------------
# 4️⃣ NMF (TF-IDF Based)
# ------------------------------
tfidf_vectorizer = TfidfVectorizer(max_df=0.9, min_df=5, ngram_range=(1,2))
X_tfidf = tfidf_vectorizer.fit_transform(df["clean_text"])

nmf = NMF(n_components=NUM_TOPICS, random_state=42)
nmf.fit(X_tfidf)

df["nmf_topic"] = nmf.transform(X_tfidf).argmax(axis=1)

# ------------------------------
# 5️⃣ Print Top Words Per Topic
# ------------------------------
def print_topics(model, feature_names, n_words=10):
    for topic_idx, topic in enumerate(model.components_):
        top_features = topic.argsort()[-n_words:][::-1]
        top_words = [feature_names[i] for i in top_features]
        print(f"\nTopic {topic_idx}:")
        print(", ".join(top_words))

def extract_topic_words(model, feature_names, n_words=10):
    topic_words = {}
    for topic_idx, topic in enumerate(model.components_):
        top_features = topic.argsort()[-n_words:][::-1]
        topic_words[topic_idx] = [feature_names[i] for i in top_features]
    return topic_words

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()
LABEL_NMF = os.getenv("LABEL_NMF", "").strip().lower() in {"1", "true", "yes", "y"}

def label_topic_groq(words):
    if not GROQ_API_KEY:
        raise RuntimeError("Missing GROQ_API_KEY env var")

    try:
        import requests  # type: ignore
    except ModuleNotFoundError as e:
        raise RuntimeError("Missing dependency: requests. Install with: pip install requests") from e

    prompt = (
        "These are top words from a topic:\n"
        f"{', '.join(words)}\n\n"
        "Return ONLY a short 2-3 word narrative label. No quotes. No punctuation."
    )

    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "Return only the label text."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 16,
        },
        timeout=30,
    )
    r.raise_for_status()
    label = r.json()["choices"][0]["message"]["content"].strip()
    return label.strip().strip('"').strip("'")

print("\n=== LDA Topics ===")
print_topics(lda, count_vectorizer.get_feature_names_out())

print("\n=== NMF Topics ===")
print_topics(nmf, tfidf_vectorizer.get_feature_names_out())

# ------------------------------
# 5️⃣b Label Topics (Groq, Optional)
# ------------------------------
lda_topic_words = extract_topic_words(lda, count_vectorizer.get_feature_names_out())
nmf_topic_words = extract_topic_words(nmf, tfidf_vectorizer.get_feature_names_out())
lda_topic_labels = None

if GROQ_API_KEY:
    try:
        lda_topic_labels = {tid: label_topic_groq(words) for tid, words in lda_topic_words.items()}
        print("\n=== LDA Topic Labels (Groq) ===")
        print(lda_topic_labels)

        if LABEL_NMF:
            nmf_topic_labels = {tid: label_topic_groq(words) for tid, words in nmf_topic_words.items()}
            print("\n=== NMF Topic Labels (Groq) ===")
            print(nmf_topic_labels)
    except Exception as e:
        print(f"\nGroq labeling failed: {e}")
else:
    print("\nSkipping Groq labeling (set GROQ_API_KEY to enable).")

# ------------------------------
# 6️⃣ Topic Counts
# ------------------------------
print("\nLDA Topic Distribution:")
print(df["lda_topic"].value_counts())

print("\nNMF Topic Distribution:")
print(df["nmf_topic"].value_counts())

# ------------------------------
# 7️⃣ Engagement Per Topic
# ------------------------------
engagement = df.groupby("lda_topic")[["score", "num_comments"]].mean()
if lda_topic_labels:
    engagement = engagement.assign(label=engagement.index.map(lda_topic_labels))
print("\nAverage Engagement Per LDA Topic:")
print(engagement)

# ------------------------------
# 8️⃣ Topic Trends Over Time
# ------------------------------
df["created_date"] = pd.to_datetime(df["created_utc"], unit="s")
df["month"] = df["created_date"].dt.to_period("M")

topic_trend = df.groupby(["month", "lda_topic"]).size().reset_index(name="count")
print("\nTopic Trends Sample:")
print(topic_trend.head())
