import requests
import json

def fetch_analysis():
    url = "http://localhost:8001/analyze"
    payload = {
        "narrative_id": "3_propublica.org",
        "url": "https://www.propublica.org/article/inside-ziklag-secret-christian-charity-2024-election"
    }
    response = requests.post(url, json=payload)
    with open("analysis_output.json", "w", encoding="utf-8") as f:
        json.dump(response.json(), f, indent=2)
    print("Analysis saved to analysis_output.json")

if __name__ == "__main__":
    fetch_analysis()
