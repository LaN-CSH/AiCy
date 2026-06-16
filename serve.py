"""AiCy Viewer — local dev server.

Run:  python serve.py
Open: http://localhost:8080/frontend/
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

server = http.server.HTTPServer(("", PORT), handler)

url = f"http://localhost:{PORT}/frontend/"
print(f"AiCy Viewer running at {url}")
print("Press Ctrl+C to stop.\n")

threading.Timer(1.0, lambda: webbrowser.open(url)).start()

try:
    server.serve_forever()
except KeyboardInterrupt:
    print("\nStopped.")
    server.server_close()
    sys.exit(0)
