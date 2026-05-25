"""
Burrow Web 服务器 —— 为前端提供 REST API + 静态文件服务
用法: python web_server.py
然后浏览器打开 http://localhost:8080
"""

import json
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import BurrowDB

db = BurrowDB()


class BurrowHandler(SimpleHTTPRequestHandler):
    """处理前端请求 + REST API"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.join(os.path.dirname(__file__), "static"), **kwargs)

    # ==================== API 路由 ====================

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        body = self.rfile.read(length)
        return json.loads(body.decode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # 单参数解包
        def _p(key, default=""):
            v = params.get(key, [default])
            return v[0] if v else default

        try:
            if path == "/api/types":
                types = db.get_types()
                counts = db.get_type_counts()
                for t in types:
                    t["count"] = counts.get(t["type"], 0)
                self._send_json(types)

            elif path == "/api/entries":
                etype = _p("type")
                period = _p("period", "all")
                entries = db.recall(type=etype if etype else None, max_results=100)
                self._send_json(entries)

            elif path.startswith("/api/entries/"):
                eid = path.split("/")[-1]
                entry = db.get_entry(eid)
                if entry:
                    self._send_json(entry)
                else:
                    self._send_json({"error": "not found"}, 404)

            elif path == "/api/search":
                q = _p("q")
                if q:
                    entries = db.search_fts(q, 50)
                    self._send_json(entries)
                else:
                    self._send_json([])

            elif path == "/api/permanent":
                entries = db.list_permanent()
                self._send_json(entries)

            elif path == "/api/stats":
                stats = db.stats()
                self._send_json(stats)

            else:
                # 静态文件
                super().do_GET()

        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/entries":
                data = self._read_body()
                entry = db.create_entry(
                    content=data.get("content", ""),
                    type=data.get("type", "journal"),
                    title=data.get("title", ""),
                    fields=data.get("fields", {}),
                    tags=data.get("tags", ""),
                    importance=data.get("importance", 5),
                    is_permanent=data.get("is_permanent", False),
                )
                self._send_json(entry, 201)

            else:
                self._send_json({"error": "not found"}, 404)

        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path.startswith("/api/entries/"):
                eid = path.split("/")[-1]
                data = self._read_body()
                entry = db.update_entry(eid, **data)
                if entry:
                    self._send_json(entry)
                else:
                    self._send_json({"error": "not found"}, 404)

            else:
                self._send_json({"error": "not found"}, 404)

        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path.startswith("/api/entries/"):
                eid = path.split("/")[-1]
                entry = db.get_entry(eid)
                if entry:
                    db.delete_entry(eid)
                    self._send_json({"deleted": eid})
                else:
                    self._send_json({"error": "not found"}, 404)

            else:
                self._send_json({"error": "not found"}, 404)

        except Exception as e:
            self._send_json({"error": str(e)}, 500)


def main():
    port = 8080
    server = HTTPServer(("0.0.0.0", port), BurrowHandler)
    print(f"Burrow Web 服务器已启动: http://localhost:{port}")
    print("按 Ctrl+C 停止")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        server.server_close()


if __name__ == "__main__":
    main()
