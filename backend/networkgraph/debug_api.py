from fastapi.testclient import TestClient
from main import app

def test_api():
    print("Initializing TestClient...")
    with TestClient(app) as client:
        print("Making request to /graph...")
        try:
            response = client.get("/graph")
            print(f"Status Code: {response.status_code}")
            if response.status_code != 200:
                print(f"Response Body: {response.text}")
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_api()
