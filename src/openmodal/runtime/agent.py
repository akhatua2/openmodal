"""Execution agent that runs inside containers.

Receives function calls as (module_name, function_name, pickled_args),
imports the function by name, executes it, and returns the pickled result.

Start with: python -m openmodal.runtime.agent --port 50051
"""

from __future__ import annotations

import importlib
import json
import logging
import pickle
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger("openmodal.agent")

DEFAULT_PORT = 50051


class AgentHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/execute":
            self._handle_execute()
        elif self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def _handle_execute(self):
        import asyncio
        import inspect

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            request = json.loads(body.split(b"\n", 1)[0])
            args_data = body.split(b"\n", 1)[1] if b"\n" in body else b""

            module_name = request["module"]
            function_name = request["function"]

            # Import the user module before unpickling args, because pickled
            # objects (e.g. dataclasses) reference their defining module.
            # Also register as "_user_app" since that's how the client loads it.
            module = importlib.import_module(module_name)
            sys.modules["_user_app"] = module

            args, kwargs = pickle.loads(args_data) if args_data else ((), {})
            func = getattr(module, function_name)
            raw_func = getattr(func, "__wrapped__", func)

            if inspect.iscoroutinefunction(raw_func):
                result = asyncio.run(raw_func(*args, **kwargs))
            else:
                result = func(*args, **kwargs)

            response_body = pickle.dumps({"ok": True, "result": result})
        except Exception:
            tb = traceback.format_exc()
            logger.error(f"Execution error: {tb}")
            try:
                response_body = pickle.dumps({"ok": False, "error": tb, "traceback": tb})
            except Exception:
                response_body = json.dumps({"ok": False, "error": tb, "traceback": tb}).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _respond(self, status: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        logger.debug(format, *args)


def serve(port: int = DEFAULT_PORT):
    server = HTTPServer(("0.0.0.0", port), AgentHandler)
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    serve(args.port)
