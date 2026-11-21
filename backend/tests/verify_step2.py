import urllib.request
import json

def test_endpoint(url, name):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Antigravity-Verifier/1.0"})
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            body_preview = raw.decode("utf-8", errors="replace")[:250]
            print(f"=== {name} ===")
            print(f"URL: {url}")
            print(f"HTTP Status: {status}")
            print(f"Content-Type: {content_type}")
            print(f"Body: {body_preview}\n")
    except Exception as e:
        print(f"=== {name} FAILED ===")
        print(f"Error: {e}\n")

if __name__ == "__main__":
    test_endpoint("http://127.0.0.1:8000/", "Root Endpoint")
    test_endpoint("http://127.0.0.1:8000/api/health", "Health Endpoint")
    test_endpoint("http://127.0.0.1:8000/docs", "Swagger Docs Endpoint")
    test_endpoint("http://127.0.0.1:8000/openapi.json", "OpenAPI Spec Endpoint")
