"""Local lab notification endpoint; received alerts are logged as JSON."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class AlertHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/alerts":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 1024 * 1024:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict) or not isinstance(payload.get("alerts"), list):
                self.send_error(400)
                return
        except (ValueError, UnicodeError):
            self.send_error(400)
            return
        print(json.dumps({
            "event": "alert_notification", "status": payload.get("status"),
            "alerts": [{"status": a.get("status"), "labels": a.get("labels", {})}
                       for a in payload["alerts"] if isinstance(a, dict)],
        }), flush=True)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"received":true}\n')


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 5001), AlertHandler).serve_forever()
