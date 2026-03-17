import argparse
import json
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from mvp.backend.pcu_pipeline import build_payload  # noqa: E402


class PCUServer(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/pcu":
            self.handle_pcu(parsed)
            return
        super().do_GET()

    def handle_pcu(self, parsed):
        params = urllib.parse.parse_qs(parsed.query)
        dataset = params.get("dataset", ["CGMacros-015"])[0]
        participant = params.get("participant", [None])[0]
        max_meals = params.get("max_meals", ["6"])[0]

        try:
            max_meals = int(max_meals)
        except ValueError:
            max_meals = 6

        dataset_path = (self.server.root_dir / dataset).resolve()
        if not str(dataset_path).startswith(str(self.server.root_dir)):
            self.send_error(400, "Invalid dataset path.")
            return
        if not dataset_path.exists():
            self.send_error(404, "Dataset not found.")
            return

        payload = build_payload(dataset_path, participant=participant, max_meals=max_meals)
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    parser = argparse.ArgumentParser(description="PCU MVP backend server.")
    parser.add_argument("--port", type=int, default=8000, help="Port to serve.")
    args = parser.parse_args()

    root_dir = ROOT_DIR
    handler = lambda *handler_args, **handler_kwargs: PCUServer(
        *handler_args, directory=str(root_dir), **handler_kwargs
    )
    server = ThreadingHTTPServer(("", args.port), handler)
    server.root_dir = root_dir
    print(f"Serving PCU MVP on http://localhost:{args.port}/mvp/ui/")
    server.serve_forever()


if __name__ == "__main__":
    main()
