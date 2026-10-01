"""Double-click launcher; reuse a running instance of this app."""
import json
from pathlib import Path
import threading
import urllib.request
import webbrowser


def main():
    url = "http://127.0.0.1:8765"
    try:
        with urllib.request.urlopen(url + "/api/status", timeout=2) as response:
            status = json.load(response)
        if "vault_path" in status and "codex" in status:
            webbrowser.open(url)
            return
    except Exception:
        pass
    from .server import main as serve
    def open_when_ready():
        import time
        for _ in range(30):
            try:
                with urllib.request.urlopen(url + "/api/status", timeout=2):
                    webbrowser.open(url)
                    return
            except Exception:
                time.sleep(0.5)
    threading.Thread(target=open_when_ready, daemon=True).start()
    serve()


if __name__ == "__main__":
    main()
