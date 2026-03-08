import os
import requests
from dotenv import load_dotenv

load_dotenv(dotenv_path=".env")

headers = {
    "Authorization": f"Bearer {os.getenv('GROQ_API_KEY')}"
}
r = requests.get("https://api.groq.com/openai/v1/models", headers=headers)
try:
    models = r.json().get('data', [])
    print("Available Models:")
    for m in models:
        print(f"- {m['id']}")
except Exception as e:
    print(f"Error fetching models: {e}")
    print(r.text)
