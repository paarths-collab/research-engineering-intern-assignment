import os
import json
import time
import praw
from groq import Groq
from geopy.geocoders import Nominatim
from dotenv import load_dotenv
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

# -------------------------------
# Initialize Reddit
# -------------------------------
reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT")
)

# -------------------------------
# Initialize Sentiment Analyzer
# -------------------------------
analyzer = SentimentIntensityAnalyzer()

# -------------------------------
# Initialize Groq
# -------------------------------
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# -------------------------------
# Rate Limit Decorator
# -------------------------------
def with_rate_limit_retry(max_retries=3, wait_secs=60):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if "429" in str(e) or "rate_limit" in str(e).lower():
                        print(f"Rate limit hit. Waiting {wait_secs} seconds... (Attempt {attempt + 1}/{max_retries})")
                        time.sleep(wait_secs)
                    else:
                        raise e
            return func(*args, **kwargs) # Last attempt
        return wrapper
    return decorator

# -------------------------------
# Initialize Geocoder
# -------------------------------
geolocator = Nominatim(user_agent="geo_pipeline_test")

# -------------------------------
# Normalization Dictionary
# -------------------------------
NORMALIZE = {
    "US": "United States",
    "U.S.": "United States",
    "USA": "United States",
    "Russian": "Russia",
    "Iranian": "Iran",
    "Israeli": "Israel",
    "Ukrainian": "Ukraine",
    "Qatari": "Qatar"
}

# -------------------------------
# Simple In-Memory Cache
# -------------------------------
geo_cache = {}

# -------------------------------
# Extract PRIMARY Event Location
# -------------------------------
import re

@with_rate_limit_retry()
def _call_groq(prompt, system_message="You extract primary event locations and return only raw JSON arrays.", model="llama-3.1-8b-instant", temperature=0):
    return groq_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature
    )

def extract_event_location(text):
    prompt = f"""
    Identify the PRIMARY physical location where the main event is happening.

    Rules:
    - If a specific city is mentioned, prefer the city over the country.
    - If only a country is mentioned, return the country.
    - Convert nationality adjectives (e.g., Iranian, Russian) to country names.
    - Return ONLY a valid JSON array with ONE location.
    - Example: ["Riyadh"] or ["Iran"]

    Text:
    {text}
    """

    response = _call_groq(prompt)
    content = response.choices[0].message.content.strip()
    print("RAW LLM OUTPUT:", content)

    # Remove markdown blocks if any
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)

    match = re.search(r"\[.*?\]", content, re.DOTALL)

    if match:
        json_part = match.group(0)
        try:
            locations = json.loads(json_part)

            cleaned = []
            for loc in locations:
                loc = NORMALIZE.get(loc, loc)

                # Remove junk like "Global"
                if loc.lower() not in ["global", "world"]:
                    cleaned.append(loc)

            return cleaned

        except:
            pass

    return []

# -------------------------------
# Geocode Function with Cache
# -------------------------------
def geocode_location(name):

    if name in geo_cache:
        return geo_cache[name]

    try:
        location = geolocator.geocode(name, timeout=10)
        time.sleep(1)  # avoid rate limit

        if location:
            geo_data = {
                "name": name,
                "lat": location.latitude,
                "lon": location.longitude
            }

            geo_cache[name] = geo_data
            return geo_data

    except Exception as e:
        print("Geocode error:", e)

    return None

# -------------------------------
# Aggregate By Location
# -------------------------------
def aggregate_by_location(results):

    aggregated = {}

    for item in results:
        key = item["location"]

        if key not in aggregated:
            aggregated[key] = {
                "location": key,
                "lat": item["lat"],
                "lon": item["lon"],
                "events": []
            }

        aggregated[key]["events"].append(item)

    return list(aggregated.values())


# -------------------------------
# Meta Stats Layer
# -------------------------------
def get_meta_stats(events):
    subreddits = set(e["subreddit"] for e in events)
    authors = set(e["author"] for e in events)
    total_score = sum(e["score"] for e in events)
    total_comments = sum(e["num_comments"] for e in events)

    return {
        "total_subreddits": len(subreddits),
        "total_posts": len(events),
        "active_users": len(authors),
        "total_interactions": total_score + total_comments
    }


# -------------------------------
# Interaction Intelligence
# -------------------------------
from collections import Counter

def get_interaction_intelligence(events):
    if not events:
        return {}

    most_liked = max(events, key=lambda e: e["score"])
    most_commented = max(events, key=lambda e: e["num_comments"])

    # Trending Topics (Keyword Frequency)
    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "with", "of", "by", "is", "are", "was", "were", "it", "that", "this", "be", "has", "have", "from", "as", "about",
        "up", "down", "out", "over", "under", "after", "again", "then", "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other",
        "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "can", "will", "just", "should", "now", "says", "says", "said", "new", "daily", "live", "thread",
        "part", "part", "r", "worldnews", "news", "post", "video", "report"
    }
    all_text = " ".join(e["event"] for e in events).lower()
    words = re.findall(r"\w+", all_text)
    filtered_words = [w for w in words if w not in STOPWORDS and len(w) > 2]
    common = Counter(filtered_words).most_common(10)

    return {
        "most_liked": {
            "title": most_liked["event"],
            "score": most_liked["score"],
            "subreddit": most_liked["subreddit"]
        },
        "most_commented": {
            "title": most_commented["event"],
            "num_comments": most_commented["num_comments"],
            "subreddit": most_commented["subreddit"]
        },
        "trending_topics": [topic for topic, count in common]
    }

# -------------------------------
# Audience Mood (VADER)
# -------------------------------
def compute_sentiment(events):
    pos = neg = neu = 0

    for e in events:
        score = analyzer.polarity_scores(e["event"])
        compound = score["compound"]

        if compound > 0.05:
            pos += 1
        elif compound < -0.05:
            neg += 1
        else:
            neu += 1

    total = pos + neg + neu
    return {
        "positive": round((pos/total)*100, 1) if total else 0,
        "negative": round((neg/total)*100, 1) if total else 0,
        "neutral": round((neu/total)*100, 1) if total else 0
    }

# -------------------------------
# Narrative Synthesis (LLM-Grounding)
# -------------------------------
def generate_narrative_intel(cluster, meta, interaction, advanced, mood):
    top_post_title = interaction.get("most_liked", {}).get("title", "N/A")
    top_comment_title = interaction.get("most_commented", {}).get("title", "N/A")
    bullet_list_of_titles = "\n".join([f"- {e['event']} (Subreddit: {e['subreddit']})" for e in cluster["events"]])

    prompt = f"""
    You are a geopolitical intelligence analyst for SimPPL.

    Narrative Location: {cluster['location']}
    Total Posts: {meta['total_posts']}
    Total Interactions: {meta['total_interactions']}
    Cross-Community Spread: {advanced['spread_score']}
    Velocity: {advanced['velocity_stage']}
    
    Data Context:
    Sentiment (VADER): {mood['sentiment']}
    Dominant Emotion: {mood['emotions']}

    Top Engaged Post:
    "{top_post_title}"

    Most Commented Post:
    "{top_comment_title}"

    All Headlines:
    {bullet_list_of_titles}

    Write:
    1. Executive summary (4–6 sentences, high-level analytical tone, ground in data).
    2. 5 key themes (strategic Geopolitical level).
    3. 3 strategic insights (forward-looking implications).

    Return STRICT JSON with exactly this structure:

    {{
      "summary": "Professional analytical summary",
      "key_themes": ["theme1", "theme2", "theme3", "theme4", "theme5"],
      "key_actors": ["actor1", "actor2"],
      "strategic_insights": ["insight1", "insight2", "insight3"]
    }}

    Return ONLY valid JSON.
    """

    response = _call_groq(prompt, system_message="You extract geopolitical intelligence and return only raw JSON.", model="llama-3.3-70b-versatile", temperature=0.1)
    content = response.choices[0].message.content.strip()

    # Generic cleaning
    content = re.sub(r"```json", "", content, flags=re.IGNORECASE)
    content = re.sub(r"```", "", content)

    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        try:
            return json.loads(match.group(0))
        except:
            pass

    print(f"⚠ Failed to parse narrative JSON for {cluster['location']}")
    return {}

# -------------------------------
# Audience Mood Insights
# -------------------------------
def get_audience_mood(events):
    headlines = [e["event"] for e in events]
    prompt = f"""
    Analyze the audience emotions (Anger, Joy, Fear, Sadness) for these headlines:
    {headlines}

    Return STRICT JSON:
    {{
      "emotions": {{ "anger": %, "joy": %, "fear": %, "sadness": % }}
    }}
    Total emotions must be 100%.
    """

    response = _call_groq(prompt, system_message="Return only valid JSON.", model="llama-3.1-8b-instant", temperature=0.1)
    content = response.choices[0].message.content.strip()
    content = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
    match = re.search(r"\{.*\}", content, re.DOTALL)
    
    vader_sentiment = compute_sentiment(events)
    
    if match:
        try:
            emotions = json.loads(match.group(0)).get("emotions", {})
            return {
                "sentiment": vader_sentiment,
                "emotions": emotions
            }
        except:
            pass
            
    return {
        "sentiment": vader_sentiment,
        "emotions": {"anger": 0, "joy": 0, "fear": 0, "sadness": 0}
    }

# -------------------------------
# Escalation Detector (Deterministic)
# -------------------------------
def compute_risk(events):
    RISK_WORDS = ["attack", "strike", "war", "blast", "death", "retaliate", "invasion", "killing", "bombing", "nuclear", "escalate", "conflict"]
    
    matches = 0
    for e in events:
        text = e["event"].lower()
        if any(w in text for w in RISK_WORDS):
            matches += 1
            
    return round(matches / len(events), 2) if events else 0


# -------------------------------
# Advanced Metrics
# -------------------------------
def get_advanced_metrics(events):
    if not events:
        return {}

    # 1. Narrative Concentration (Gini-like index on interactions)
    interactions = [e["score"] + e["num_comments"] for e in events]
    total_interactions = sum(interactions)
    if total_interactions > 0:
        max_inter = max(interactions)
        concentration = round(max_inter / total_interactions, 2)
    else:
        concentration = 0

    # 2. Cross-Community Spread
    subs = set(e["subreddit"] for e in events)
    spread = "High" if len(subs) > 3 else "Medium" if len(subs) > 1 else "Low"

    # 3. Velocity Score
    times = [e["created_utc"] for e in events]
    if len(times) > 1:
        time_range = max(times) - min(times)
        if time_range > 0:
            events_per_hour = (len(events) / (time_range / 3600))
            velocity = "Escalating" if events_per_hour > 1 else "Emerging"
        else:
            velocity = "Peak"
    else:
        velocity = "Emerging"

    # 4. Polarization Score
    # Variance in sentiment between subreddits
    if len(subs) > 1:
        sentiment_per_sub = []
        for s in subs:
            sub_events = [e for e in events if e["subreddit"] == s]
            s_mood = compute_sentiment(sub_events)
            sentiment_per_sub.append(s_mood["negative"])
        
        # Simple variance
        mean = sum(sentiment_per_sub) / len(sentiment_per_sub)
        variance = sum((x - mean) ** 2 for x in sentiment_per_sub) / len(sentiment_per_sub)
        polarization = round(min(variance / 100, 1.0), 2) # normalize
    else:
        polarization = 0

    return {
        "concentration_index": concentration,
        "spread_score": spread,
        "velocity_stage": velocity,
        "polarization_score": polarization,
        "risk_index": compute_risk(events)
    }


# -------------------------------
# Build SimPPL Narrative Objects
# -------------------------------
def build_simppl_dashboard(results):

    clusters = aggregate_by_location(results)

    narratives = []

    for cluster in clusters:
        events = cluster["events"]
        
        # 1. Analytics Layers
        meta = get_meta_stats(events)
        interaction = get_interaction_intelligence(events)
        mood = get_audience_mood(events)
        advanced = get_advanced_metrics(events)

        # 2. Narrative synthesis (LLM with Grounding)
        intel = generate_narrative_intel(cluster, meta, interaction, advanced, mood)

        # 3. Physical Location + Cluster headlines
        location_data = {
            "location": cluster["location"],
            "lat": cluster["lat"],
            "lon": cluster["lon"]
        }

        # 4. Final SimPPL Intelligence Structure
        narrative_object = {
            "title": cluster["location"] + " Narrative Analysis",
            "location": location_data,
            "meta_stats": meta,
            "executive_summary": intel.get("summary"),
            "key_findings": intel.get("strategic_insights"),
            "interaction_points": interaction,
            "audience_mood": mood,
            "advanced_metrics": advanced
        }

        narratives.append(narrative_object)

    return narratives


# -------------------------------
# Pipeline
# -------------------------------
def run_pipeline(return_results=False):

    subreddits = ["worldnews", "news", "geopolitics", "europe", "asia"]
    
    results = []
    seen_events = set()

    for sub_name in subreddits:
        print(f"\nScanning r/{sub_name}...")
        subreddit = reddit.subreddit(sub_name)
    
        for post in subreddit.hot(limit=10):

            if post.title in seen_events:
                continue

            seen_events.add(post.title)

            print("\n----------------------------------")
            print("Title:", post.title)

            locations = extract_event_location(post.title)
            print("Extracted Location:", locations)

            for loc in locations:
                geo = geocode_location(loc)

                if geo:
                    event_data = {
                        "event": post.title,
                        "location": geo["name"],
                        "lat": geo["lat"],
                        "lon": geo["lon"],
                        "subreddit": post.subreddit.display_name,
                        "author": post.author.name if post.author else "[deleted]",
                        "score": post.score,
                        "num_comments": post.num_comments,
                        "created_utc": post.created_utc
                    }

                    results.append(event_data)
                    print("Mapped:", event_data)

    # 🔥 BUILD SIMPPL INTEL DASHBOARD OBJECT
    simppl_output = build_simppl_dashboard(results)

    print("\n================ SIMPPL INTELLIGENCE OUTPUT ================")
    print(json.dumps(simppl_output, indent=2))


if __name__ == "__main__":
    run_pipeline()
