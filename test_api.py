"""
API Test Script - Demonstrates programmatic usage of Shock Response Analyzer
Run this after starting the server with: python main.py
"""

import requests
import json

API_URL = "http://localhost:8000"

def test_api():
    print("🔬 Shock Response Analyzer - API Test")
    print("=" * 50)
    print()
    
    # Test 1: Check API status
    print("1️⃣  Testing API status...")
    response = requests.get(f"{API_URL}/")
    if response.status_code == 200:
        print("✓ API is running")
        print(f"   Status: {response.json()}")
    else:
        print("✗ API is not responding")
        return
    print()
    
    # Test 2: Get events list
    print("2️⃣  Fetching global events...")
    response = requests.get(f"{API_URL}/events")
    if response.status_code == 200:
        events = response.json()["events"]
        print(f"✓ Found {len(events)} events:")
        for event in events:
            print(f"   - {event['date']}: {event['title']}")
    print()
    
    # Test 3: Upload data (example - you need to provide the file path)
    print("3️⃣  Upload data file...")
    print("   To upload data, use:")
    print("   ```python")
    print("   with open('data.jsonl', 'rb') as f:")
    print("       files = {'file': f}")
    print("       response = requests.post(f'{API_URL}/upload', files=files)")
    print("   ```")
    print()
    
    # Test 4: Analyze event (example)
    print("4️⃣  Example: Analyze U.S. Presidential Election")
    print("   Request:")
    payload = {
        "event_id": 3,  # U.S. Presidential Election
        "days_before": 7,
        "days_after": 7
    }
    print(f"   {json.dumps(payload, indent=4)}")
    print()
    print("   To run analysis:")
    print("   ```python")
    print(f"   response = requests.post('{API_URL}/analyze', json={payload})")
    print("   result = response.json()")
    print("   print(result['analysis'])")
    print("   ```")
    print()
    
    print("=" * 50)
    print("✓ API test complete!")
    print()
    print("Next steps:")
    print("1. Upload your data.jsonl file")
    print("2. Call /analyze endpoint with event_id")
    print("3. Process the 4-dimensional analysis results")

if __name__ == "__main__":
    try:
        test_api()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to API")
        print("   Make sure the server is running:")
        print("   python main.py")
    except Exception as e:
        print(f"❌ Error: {e}")
