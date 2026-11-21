import urllib.request
import json
import sys

def verify():
    # 1. Backend direct
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/") as resp:
            data = json.loads(resp.read().decode())
            print(f"[VERIFIED] Direct Backend Root: {data['project']} status={data['status']}")
    except Exception as e:
        print(f"[FAILED] Direct Backend Root: {e}")
        sys.exit(1)

    # 2. Backend health
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health") as resp:
            data = json.loads(resp.read().decode())
            print(f"[VERIFIED] Direct Backend Health: status={data['status']}, env={data['environment']}")
    except Exception as e:
        print(f"[FAILED] Direct Backend Health: {e}")
        sys.exit(1)

    # 3. Frontend proxy to backend
    try:
        with urllib.request.urlopen("http://127.0.0.1:5173/api/health") as resp:
            data = json.loads(resp.read().decode())
            print(f"[VERIFIED] Frontend Vite Proxy -> Backend: status={data['status']}")
    except Exception as e:
        print(f"[FAILED] Frontend Vite Proxy -> Backend: {e}")
        sys.exit(1)

    # 4. Frontend root page
    try:
        with urllib.request.urlopen("http://127.0.0.1:5173/") as resp:
            html = resp.read().decode()
            has_root = "root" in html
            print(f"[VERIFIED] Frontend Index Page: status=200, has_root_element={has_root}")
    except Exception as e:
        print(f"[FAILED] Frontend Index Page: {e}")
        sys.exit(1)

    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY.")

if __name__ == "__main__":
    verify()
