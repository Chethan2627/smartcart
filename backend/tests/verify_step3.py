import urllib.request

def test_frontend():
    url = "http://127.0.0.1:5173/"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Antigravity-Verifier/1.0"})
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            html = resp.read().decode("utf-8")
            has_root = '<div id="root">' in html
            has_vite_client = '@vite/client' in html
            print("=== Frontend Vite Server ===")
            print(f"URL: {url}")
            print(f"HTTP Status: {status}")
            print(f"Content-Type: {content_type}")
            print(f"Contains <div id=\"root\">: {has_root}")
            print(f"Contains Vite client script: {has_vite_client}")
            print(f"HTML snippet:\n{html[:250]}\n")
    except Exception as e:
        print(f"Frontend test FAILED: {e}")

if __name__ == "__main__":
    test_frontend()
