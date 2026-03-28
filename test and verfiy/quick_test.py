import requests

url = "http://localhost:8000/api/chat"
data = {"query": "Give me a count of posts in r/Conservative."}

print(f"🚀 Sending query: {data['query']}")
try:
    response = requests.post(url, json=data)

    if response.status_code == 200:
        print("✅ Result from Agent:")
        print(response.json())
    else:
        print(f"❌ Error {response.status_code}:")
        print(response.text)
except Exception as e:
    print(f"❌ Connection Error: {e}")
