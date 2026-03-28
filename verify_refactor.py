import requests
import json

base_url = "http://localhost:8000/api/network/intelligence"
endpoints = [
    "/narratives",
    "/graph?mode=spread",
    "/timeline",
    "/search?q=Trump",
    "/subreddit/politics/ecosystem",
    "/leaderboard"
]

results = {}

for ep in endpoints:
    try:
        url = base_url + ep
        resp = requests.get(url, timeout=10)
        results[ep] = {
            "status": resp.status_code,
            "error": resp.text if resp.status_code != 200 else None,
            "data_summary": {k: len(v) if isinstance(v, list) else v for k, v in resp.json().items()} if resp.status_code == 200 else None
        }
    except Exception as e:
        results[ep] = {"status": "ERROR", "error": str(e)}

print(json.dumps(results, indent=2))
