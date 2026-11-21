import urllib.request
import json

def test_frontend_backend_communication():
    # 1. Test proxy endpoint: http://127.0.0.1:5173/api/health
    proxy_url = "http://127.0.0.1:5173/api/health"
    print("=== Step 4: Frontend-to-Backend Communication via Vite Proxy ===")
    print(f"Requesting: {proxy_url}")
    try:
        req = urllib.request.Request(proxy_url, headers={"User-Agent": "SmartCart-Client/1.0"})
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
            data = json.loads(raw.decode("utf-8"))
            print(f"HTTP Status: {status}")
            print(f"Content-Type: {content_type}")
            print(f"Proxied JSON Response: {json.dumps(data, indent=2)}")
            print("Vite Proxy Communication: PASSED\n")
    except Exception as e:
        print(f"Vite Proxy Communication: FAILED ({e})\n")

    # 2. Check API client configuration in frontend/src/api/client.ts
    print("=== API Client Configuration Analysis (frontend/src/api/client.ts) ===")
    with open("frontend/src/api/client.ts", "r", encoding="utf-8") as f:
        client_code = f.read()
    
    for line in client_code.splitlines():
        if "API_BASE_URL" in line:
            print(f"Configured API_BASE_URL line: {line.strip()}")
            if "'http://localhost:8000'" in line:
                print("Note: In development, API_BASE_URL currently defaults to 'http://localhost:8000', bypassing the Vite reverse proxy (/api) if not overridden.")
                print("Recommendation: Set API_BASE_URL default to '' (empty string) so relative requests like /api/health utilize Vite's proxy in dev, and set VITE_API_URL in production.")

if __name__ == "__main__":
    test_frontend_backend_communication()
