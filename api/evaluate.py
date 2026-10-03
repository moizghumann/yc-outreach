"""Validate an evidence card. Does not fetch supplied URLs or send messages."""
import json
from http.server import BaseHTTPRequestHandler
from prospecting import evaluate

MAX_BODY = 256_000


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Card must be between 1 and 256000 bytes')
            card = json.loads(self.rfile.read(length))
            if not isinstance(card, dict):
                raise ValueError('Expected one research-card object')
            body, status = evaluate(card), 200
        except (ValueError, TypeError, AttributeError) as err:
            body, status = {'error': str(err)}, 400
        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
