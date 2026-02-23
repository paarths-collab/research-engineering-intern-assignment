"""
Shock Response Analyzer - FastAPI Backend
Analyzes structural shifts in Reddit communities after real-world events
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json
import numpy as np
from collections import Counter, defaultdict
import math

app = FastAPI(title="Shock Response Analyzer")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global data storage
reddit_data = []

# Event definitions
GLOBAL_EVENTS = [
    {
        "id": 1,
        "date": "2024-09-27",
        "title": "Hassan Nasrallah Assassination",
        "description": "Hezbollah leader killed in Israeli airstrike"
    },
    {
        "id": 2,
        "date": "2024-10-26",
        "title": "Israeli Airstrikes on Iran",
        "description": "Significant strikes on Iranian missile facilities"
    },
    {
        "id": 3,
        "date": "2024-11-05",
        "title": "U.S. Presidential Election",
        "description": "Donald Trump wins presidency"
    },
    {
        "id": 4,
        "date": "2024-12-08",
        "title": "Assad Regime Collapse",
        "description": "Syrian government falls after 14 years of civil war"
    },
    {
        "id": 5,
        "date": "2025-01-20",
        "title": "Trump Inauguration",
        "description": "Donald Trump inaugurated as U.S. President"
    }
]


class EventAnalysisRequest(BaseModel):
    event_id: int
    days_before: int = 7
    days_after: int = 7


def parse_jsonl(content: str) -> List[Dict]:
    """Parse JSONL file and extract relevant fields"""
    posts = []
    for line in content.strip().split('\n'):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            data = obj.get('data', {})
            
            post = {
                'created_utc': data.get('created_utc'),
                'score': data.get('score', 0),
                'num_comments': data.get('num_comments', 0),
                'title': data.get('title', ''),
                'selftext': data.get('selftext', ''),
                'subreddit': data.get('subreddit', ''),
                'author': data.get('author', ''),
                'upvote_ratio': data.get('upvote_ratio', 0),
                'is_self': data.get('is_self', False),
                'url': data.get('url', '')
            }
            
            if post['created_utc']:
                posts.append(post)
        except Exception as e:
            continue
    
    return posts


def utc_to_datetime(utc_timestamp):
    """Convert UTC timestamp to datetime"""
    return datetime.fromtimestamp(utc_timestamp)


def get_posts_in_range(posts, start_date, end_date):
    """Filter posts within date range"""
    return [
        p for p in posts
        if start_date <= utc_to_datetime(p['created_utc']) <= end_date
    ]


# ============================================
# ANALYSIS DIMENSION 1: Activity Shock
# ============================================

def calculate_activity_shock(before_posts, after_posts, days_before, days_after):
    """
    Calculate posting rate change
    Metric: posts_per_day_after / posts_per_day_before
    """
    before_rate = len(before_posts) / days_before if days_before > 0 else 0
    after_rate = len(after_posts) / days_after if days_after > 0 else 0
    
    shock_ratio = after_rate / before_rate if before_rate > 0 else 0
    
    # Daily breakdown
    before_daily = defaultdict(int)
    after_daily = defaultdict(int)
    
    for post in before_posts:
        date = utc_to_datetime(post['created_utc']).date()
        before_daily[str(date)] += 1
    
    for post in after_posts:
        date = utc_to_datetime(post['created_utc']).date()
        after_daily[str(date)] += 1
    
    return {
        'before_rate': round(before_rate, 2),
        'after_rate': round(after_rate, 2),
        'shock_ratio': round(shock_ratio, 2),
        'percent_change': round((shock_ratio - 1) * 100, 2),
        'before_daily': dict(before_daily),
        'after_daily': dict(after_daily),
        'interpretation': interpret_activity_shock(shock_ratio)
    }


def interpret_activity_shock(ratio):
    """Interpret the activity shock ratio"""
    if ratio > 1.5:
        return "Major spike in activity"
    elif ratio > 1.2:
        return "Moderate increase in activity"
    elif ratio > 0.8:
        return "Stable activity level"
    elif ratio > 0.5:
        return "Moderate decrease in activity"
    else:
        return "Significant drop in activity"


# ============================================
# ANALYSIS DIMENSION 2: Discussion Intensity
# ============================================

def calculate_discussion_intensity(before_posts, after_posts):
    """
    Measure engagement change
    Metric: median(comments/post) change
    """
    before_comments = [p['num_comments'] for p in before_posts]
    after_comments = [p['num_comments'] for p in after_posts]
    
    before_median = np.median(before_comments) if before_comments else 0
    after_median = np.median(after_comments) if after_comments else 0
    
    before_mean = np.mean(before_comments) if before_comments else 0
    after_mean = np.mean(after_comments) if after_comments else 0
    
    # Comment distribution
    before_dist = create_distribution(before_comments)
    after_dist = create_distribution(after_comments)
    
    change_ratio = after_median / before_median if before_median > 0 else 0
    
    return {
        'before_median': round(before_median, 2),
        'after_median': round(after_median, 2),
        'before_mean': round(before_mean, 2),
        'after_mean': round(after_mean, 2),
        'change_ratio': round(change_ratio, 2),
        'percent_change': round((change_ratio - 1) * 100, 2),
        'before_distribution': before_dist,
        'after_distribution': after_dist,
        'interpretation': interpret_discussion_intensity(change_ratio)
    }


def create_distribution(values):
    """Create distribution buckets for visualization"""
    if not values:
        return []
    
    buckets = [0, 5, 10, 25, 50, 100, 500, 1000, 5000]
    counts = []
    
    for i in range(len(buckets) - 1):
        count = sum(1 for v in values if buckets[i] <= v < buckets[i + 1])
        counts.append({
            'range': f'{buckets[i]}-{buckets[i+1]}',
            'count': count
        })
    
    # Last bucket
    count = sum(1 for v in values if v >= buckets[-1])
    counts.append({
        'range': f'{buckets[-1]}+',
        'count': count
    })
    
    return counts


def interpret_discussion_intensity(ratio):
    """Interpret discussion intensity change"""
    if ratio > 1.5:
        return "Significantly more debate"
    elif ratio > 1.2:
        return "Increased discussion"
    elif ratio > 0.8:
        return "Stable engagement"
    elif ratio > 0.5:
        return "Reduced discussion"
    else:
        return "Significantly less debate"


# ============================================
# ANALYSIS DIMENSION 3: Attention Redistribution
# ============================================

def calculate_gini_coefficient(values):
    """
    Calculate Gini coefficient for inequality measurement
    0 = perfect equality, 1 = perfect inequality
    """
    if not values or len(values) == 0:
        return 0
    
    sorted_values = np.sort(values)
    n = len(sorted_values)
    cumsum = np.cumsum(sorted_values)
    
    return (2 * np.sum((np.arange(1, n + 1)) * sorted_values)) / (n * np.sum(sorted_values)) - (n + 1) / n


def calculate_attention_redistribution(before_posts, after_posts):
    """
    Measure if attention concentrated on few viral posts
    Metric: Δ Gini coefficient of post scores
    """
    before_scores = [p['score'] for p in before_posts if p['score'] > 0]
    after_scores = [p['score'] for p in after_posts if p['score'] > 0]
    
    before_gini = calculate_gini_coefficient(before_scores)
    after_gini = calculate_gini_coefficient(after_scores)
    
    delta_gini = after_gini - before_gini
    
    # Lorenz curve data
    before_lorenz = calculate_lorenz_curve(before_scores)
    after_lorenz = calculate_lorenz_curve(after_scores)
    
    # Top post concentration
    before_top10_pct = sum(sorted(before_scores, reverse=True)[:10]) / sum(before_scores) * 100 if before_scores else 0
    after_top10_pct = sum(sorted(after_scores, reverse=True)[:10]) / sum(after_scores) * 100 if after_scores else 0
    
    return {
        'before_gini': round(before_gini, 3),
        'after_gini': round(after_gini, 3),
        'delta_gini': round(delta_gini, 3),
        'before_lorenz': before_lorenz,
        'after_lorenz': after_lorenz,
        'before_top10_concentration': round(before_top10_pct, 2),
        'after_top10_concentration': round(after_top10_pct, 2),
        'interpretation': interpret_attention_redistribution(delta_gini, after_gini)
    }


def calculate_lorenz_curve(values):
    """Calculate Lorenz curve points for visualization"""
    if not values:
        return []
    
    sorted_values = np.sort(values)
    cumsum = np.cumsum(sorted_values)
    total = sum(sorted_values)
    
    # Sample 20 points for visualization
    indices = np.linspace(0, len(sorted_values) - 1, 20, dtype=int)
    
    points = []
    for i in indices:
        x = (i + 1) / len(sorted_values) * 100  # Percentile
        y = cumsum[i] / total * 100  # Cumulative share
        points.append({'x': round(x, 2), 'y': round(y, 2)})
    
    return points


def interpret_attention_redistribution(delta_gini, after_gini):
    """Interpret attention redistribution"""
    if delta_gini > 0.1:
        return "Attention concentrated on few viral posts"
    elif delta_gini > 0.05:
        return "Moderate concentration increase"
    elif delta_gini > -0.05:
        return "Stable attention distribution"
    elif delta_gini > -0.1:
        return "Attention became more distributed"
    else:
        return "Highly distributed attention"


# ============================================
# ANALYSIS DIMENSION 4: Topic Shift
# ============================================

def tokenize(text):
    """Simple tokenization"""
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text.split()


def calculate_tf_idf(documents):
    """Calculate TF-IDF vectors for documents"""
    # Combine all documents
    all_tokens = []
    doc_tokens = []
    
    for doc in documents:
        tokens = tokenize(doc)
        doc_tokens.append(tokens)
        all_tokens.extend(tokens)
    
    # Get vocabulary (top 100 most common words, excluding stopwords)
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                 'of', 'with', 'by', 'from', 'is', 'was', 'are', 'were', 'be', 'been',
                 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
                 'should', 'this', 'that', 'it', 'as', 'if', 'what', 'which', 'who',
                 'when', 'where', 'how', 'why', 'not', 'no', 'yes', 'can', 'may'}
    
    word_counts = Counter(all_tokens)
    vocab = [word for word, count in word_counts.most_common(200) 
             if word not in stopwords and len(word) > 2][:100]
    
    # Calculate IDF
    doc_count = len(doc_tokens)
    idf = {}
    for word in vocab:
        doc_freq = sum(1 for tokens in doc_tokens if word in tokens)
        idf[word] = math.log(doc_count / (doc_freq + 1)) if doc_freq > 0 else 0
    
    # Calculate TF-IDF vectors
    vectors = []
    for tokens in doc_tokens:
        token_counts = Counter(tokens)
        vector = []
        for word in vocab:
            tf = token_counts.get(word, 0) / len(tokens) if len(tokens) > 0 else 0
            vector.append(tf * idf.get(word, 0))
        vectors.append(vector)
    
    # Average vector for all documents
    if vectors:
        avg_vector = np.mean(vectors, axis=0)
        return avg_vector, vocab
    return np.array([]), []


def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors"""
    if len(vec1) == 0 or len(vec2) == 0:
        return 0
    
    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    
    if norm1 == 0 or norm2 == 0:
        return 0
    
    return dot_product / (norm1 * norm2)


def calculate_topic_shift(before_posts, after_posts):
    """
    Measure semantic shift in conversation topics
    Metric: cosine distance between TF-IDF vectors
    """
    before_texts = [p['title'] + ' ' + p['selftext'] for p in before_posts]
    after_texts = [p['title'] + ' ' + p['selftext'] for p in after_posts]
    
    # Get combined vocabulary
    all_texts = before_texts + after_texts
    _, vocab = calculate_tf_idf(all_texts)
    
    # Calculate TF-IDF for before and after
    before_vector, _ = calculate_tf_idf(before_texts)
    after_vector, _ = calculate_tf_idf(after_texts)
    
    # Calculate cosine similarity (and distance)
    similarity = cosine_similarity(before_vector, after_vector)
    distance = 1 - similarity
    
    # Extract top keywords
    before_keywords = extract_top_keywords(before_texts, vocab, 10)
    after_keywords = extract_top_keywords(after_texts, vocab, 10)
    
    return {
        'cosine_similarity': round(similarity, 3),
        'cosine_distance': round(distance, 3),
        'before_keywords': before_keywords,
        'after_keywords': after_keywords,
        'interpretation': interpret_topic_shift(distance)
    }


def extract_top_keywords(texts, vocab, top_n=10):
    """Extract top keywords from texts"""
    all_tokens = []
    for text in texts:
        all_tokens.extend(tokenize(text))
    
    # Count only words in vocabulary
    word_counts = Counter([token for token in all_tokens if token in vocab])
    
    return [{'word': word, 'count': count} for word, count in word_counts.most_common(top_n)]


def interpret_topic_shift(distance):
    """Interpret topic shift"""
    if distance > 0.5:
        return "Major topic shift - conversation changed dramatically"
    elif distance > 0.3:
        return "Significant topic shift"
    elif distance > 0.15:
        return "Moderate topic shift"
    elif distance > 0.05:
        return "Minor topic shift"
    else:
        return "Topics remained similar"


# ============================================
# API ENDPOINTS
# ============================================

@app.post("/upload")
async def upload_data(file: UploadFile = File(...)):
    """Upload and parse JSONL data file"""
    global reddit_data
    
    try:
        content = await file.read()
        content_str = content.decode('utf-8')
        reddit_data = parse_jsonl(content_str)
        
        # Get date range
        dates = [utc_to_datetime(p['created_utc']) for p in reddit_data]
        min_date = min(dates)
        max_date = max(dates)
        
        # Get subreddit counts
        subreddit_counts = Counter(p['subreddit'] for p in reddit_data)
        
        return {
            "success": True,
            "total_posts": len(reddit_data),
            "date_range": {
                "start": min_date.isoformat(),
                "end": max_date.isoformat()
            },
            "subreddits": dict(subreddit_counts),
            "message": f"Loaded {len(reddit_data)} posts"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/events")
async def get_events():
    """Get list of global events"""
    return {"events": GLOBAL_EVENTS}


@app.post("/analyze")
async def analyze_event(request: EventAnalysisRequest):
    """
    Analyze a specific event's impact on Reddit communities
    Returns all 4 analysis dimensions
    """
    if not reddit_data:
        raise HTTPException(status_code=400, detail="No data loaded. Please upload data first.")
    
    # Find event
    event = next((e for e in GLOBAL_EVENTS if e['id'] == request.event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    event_date = datetime.fromisoformat(event['date'])
    
    # Calculate date ranges
    before_start = event_date - timedelta(days=request.days_before)
    before_end = event_date
    after_start = event_date
    after_end = event_date + timedelta(days=request.days_after)
    
    # Get posts in ranges
    before_posts = get_posts_in_range(reddit_data, before_start, before_end)
    after_posts = get_posts_in_range(reddit_data, after_start, after_end)
    
    if not before_posts or not after_posts:
        return {
            "event": event,
            "error": "Insufficient data for this event period",
            "before_count": len(before_posts),
            "after_count": len(after_posts)
        }
    
    # Run all 4 analyses
    activity_shock = calculate_activity_shock(before_posts, after_posts, 
                                              request.days_before, request.days_after)
    
    discussion_intensity = calculate_discussion_intensity(before_posts, after_posts)
    
    attention_redistribution = calculate_attention_redistribution(before_posts, after_posts)
    
    topic_shift = calculate_topic_shift(before_posts, after_posts)
    
    return {
        "event": event,
        "date_ranges": {
            "before": {
                "start": before_start.isoformat(),
                "end": before_end.isoformat(),
                "days": request.days_before,
                "post_count": len(before_posts)
            },
            "after": {
                "start": after_start.isoformat(),
                "end": after_end.isoformat(),
                "days": request.days_after,
                "post_count": len(after_posts)
            }
        },
        "analysis": {
            "activity_shock": activity_shock,
            "discussion_intensity": discussion_intensity,
            "attention_redistribution": attention_redistribution,
            "topic_shift": topic_shift
        }
    }


@app.get("/")
async def root():
    """API status"""
    return {
        "name": "Shock Response Analyzer API",
        "version": "1.0",
        "status": "active",
        "data_loaded": len(reddit_data) > 0,
        "total_posts": len(reddit_data)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
