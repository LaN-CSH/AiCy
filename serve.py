"""AiCy Viewer — local dev server.

Run:  python serve.py
Open: http://localhost:8080/frontend/

멀티스레드 서버: 브라우저·OBS 브라우저 소스가 동시에 붙어도 안 막히고,
죽은 연결이 있어도 Ctrl+C 가 즉시 듣는다.
"""

import http.server
import os
import sys
import threading
import webbrowser

PORT = 8080

os.chdir(os.path.dirname(os.path.abspath(__file__)))

handler = http.server.SimpleHTTPRequestHandler
handler.extensions_map.update({
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".json": "application/json",
    ".wasm": "application/wasm",
})


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True  # 연결 스레드가 종료를 붙잡지 않게
    allow_reuse_address = True


server = _Server(("", PORT), handler)

url = f"http://localhost:{PORT}/frontend/"
print(f"AiCy Viewer running at {url}")
print("Press Ctrl+C to stop.\n")

if "--no-browser" not in sys.argv:
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()

try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\nStopped.")
    server.server_close()
    sys.exit(0)
