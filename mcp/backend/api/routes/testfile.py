# backend/test_endpoints.py
import requests
import sys

BASE_URL = "http://localhost:8000"

def test_endpoints():
    endpoints = ["/", "/api/health", "/api/message", "/docs", "/api/tools"] # "/openapi.json"
    
    for endpoint in endpoints:
        url = f"{BASE_URL}{endpoint}"
        try:
            response = requests.get(url, timeout=5)
            print(f"✅ {endpoint}: Status {response.status_code}")
            if response.status_code == 200:
                print(f"   Response: {response.json()}")
        except requests.exceptions.ConnectionError:
            print(f"❌ {endpoint}: Connection refused")
        except requests.exceptions.Timeout:
            print(f"❌ {endpoint}: Timeout")
        except Exception as e:
            print(f"❌ {endpoint}: Error - {str(e)}")
        print("-" * 40)

if __name__ == "__main__":
    test_endpoints()