import requests
import json
import time

def test_analyze_domain():
    print("\n--- Testing /api/analyze-domain ---")
    url = "http://127.0.0.1:8000/api/analyze-domain?domain=breitbart.com&start=2025-02-14&end=2025-02-18"
    try:
        response = requests.get(url, timeout=60)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Scraped Count: {data.get('scraped_count')}")
            print("Synthesis Result Keys:", data.get('analysis', {}).keys())
        else:
            print("Response:", response.text)
    except Exception as e:
        print(f"Error: {e}")

def test_chat(query: str):
    print(f"\n--- Testing /api/chat ---")
    print(f"Query: {query}")
    url = "http://127.0.0.1:8000/api/chat"
    payload = {"query": query}
    try:
        response = requests.post(url, json=payload, timeout=120)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            print(json.dumps(response.json(), indent=2))
        else:
            print("Response:", response.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    time.sleep(2) # Give server time to start
    test_analyze_domain()
    
    # Test cases for Chat
    test_cases = [
        "What are the top domains shared in r/politics?",
        "Are there any coordinated bot networks on r/politics related to breitbart?",
        "Which users are bridging r/Conservative and r/politics?",
    ]
    
    for case in test_cases:
        test_chat(case)
