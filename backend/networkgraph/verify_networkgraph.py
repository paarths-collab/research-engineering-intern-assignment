import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"
def test_health():
    print("\n[Test 1] Health Check")
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            print(f"Response: {json.dumps(resp.json(), indent=2)}")
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

def test_full_graph():
    print("\n[Test 2] Macro Graph (Full)")
    try:
        resp = requests.get(f"{BASE_URL}/graph")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Subreddit nodes: {len(data.get('subreddit_nodes', []))}")
            print(f"User nodes: {len(data.get('user_nodes', []))}")
            print(f"Edges: {len(data.get('edges', []))}")
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

def test_transport_chain():
    print("\n[Test 3] Narrative Transport (3_propublica.org)")
    try:
        resp = requests.get(f"{BASE_URL}/transport/3_propublica.org")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Narrative ID: {data.get('narrative_id')}")
            print(f"Total steps: {data.get('total_steps')}")
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

def test_time_filter():
    print("\n[Test 4] Temporal Filter (before=2024-01-11)")
    try:
        resp = requests.get(f"{BASE_URL}/graph/time", params={"before": "2024-01-11T00:00:00Z"})
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Edges found: {len(data.get('edges', []))}")
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

def test_user_profile():
    print("\n[Test 5] User Profile (NoGoodAtIncognito)")
    try:
        resp = requests.get(f"{BASE_URL}/user/NoGoodAtIncognito")
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Author: {data.get('author')}")
            print(f"Influence Score: {data.get('final_influence_score')}")
            return True
    except Exception as e:
        print(f"Error: {e}")
    return False

def test_analyze():
    print("\n[Test 6] AI Narrative Analysis (3_propublica.org)")
    try:
        payload = {
            "narrative_id": "3_propublica.org",
            "url": "https://www.propublica.org/article/inside-ziklag-secret-christian-charity-2024-election"
        }
        resp = requests.post(f"{BASE_URL}/analyze", json=payload)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            print(f"Analysis scrape success: {data.get('scrape_info', {}).get('success')}")
            analysis = data.get('analysis')
            if analysis:
                print(f"Analysis summary: {analysis.get('article_summary', 'None')[:100]}...")
            return True
        else:
            print(f"Response: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")
    return False

if __name__ == "__main__":
    results = [
        test_health(),
        test_full_graph(),
        test_transport_chain(),
        test_time_filter(),
        test_user_profile(),
        test_analyze()
    ]
    
    print("\n" + "="*30)
    print(f"Final Result: {sum(results)}/6 passed")
    print("="*30)
