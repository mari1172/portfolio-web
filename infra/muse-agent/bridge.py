#!/usr/bin/env python3
"""Experimental Muse pull bridge. No model or Muse login is bundled."""
import hmac
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JOBS = {}
LOCK = threading.Lock()
WAIT = int(os.environ.get("MUSE_WAIT_SECONDS", "180"))
LIMIT = 262144
CONFIG = {}
MODEL = "muse-bridge"

def valid_answer(message, request):
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return False
    content = message.get("content")
    calls = message.get("tool_calls")
    if content is not None and not isinstance(content, str):
        return False
    if not calls:
        return isinstance(content, str) and bool(content.strip())
    if not isinstance(calls, list) or len(calls) > 8:
        return False
    allowed = {t.get("function", {}).get("name") for t in request.get("tools", [])
               if isinstance(t, dict) and t.get("type") == "function"}
    ids = set()
    for call in calls:
        if not isinstance(call, dict):
            return False
        fn = call.get("function", {})
        cid = call.get("id")
        if (call.get("type") != "function" or not isinstance(cid, str) or not cid
                or cid in ids or not isinstance(fn, dict)
                or fn.get("name") not in allowed
                or not isinstance(fn.get("arguments"), str)):
            return False
        ids.add(cid)
        try:
            if not isinstance(json.loads(fn["arguments"]), dict):
                return False
        except (ValueError, TypeError):
            return False
    return True

class Handler(BaseHTTPRequestHandler):
    timeout = 20
    def log_message(self, *_):
        pass  # never log prompts or credentials

    def send(self, status, payload):
        data = json.dumps(payload).encode()
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
        except (OSError, TimeoutError):
            pass
        self.close_connection = True

    def authorized(self, role):
        header = self.headers.get("Authorization", "")
        expected = CONFIG.get(role + "_key", "")
        if not expected or not hmac.compare_digest(header, "Bearer " + expected):
            self.send(401, {"error": {"message": "Unauthorized"}})
            return False
        return True

    def read_body(self):
        try:
            size = int(self.headers.get("Content-Length", "-1"))
            if size < 0 or size > LIMIT:
                self.send(413, {"error": {"message": "Invalid body size"}})
                return None
            result = json.loads(self.rfile.read(size))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, OSError):
            self.send(400, {"error": {"message": "Invalid JSON body"}})
            return None

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/health":
            return self.send(200, {"bridge": "ready", "muse_connection": "unverified"})
        if path == "/v1/models":
            if self.authorized("user"):
                self.send(200, {"object": "list", "data": [
                    {"id": MODEL, "object": "model", "owned_by": "local-bridge"}]})
            return
        if path == "/muse/pending":
            if not self.authorized("worker"):
                return
            with LOCK:
                now = time.monotonic()
                eligible = [(jid, job) for jid, job in JOBS.items()
                            if job["deadline"] > now and job["lease"] <= now
                            and job["answer"] is None]
                result = []
                if eligible:
                    jid, job = eligible[0]
                    job["lease"] = now + 60
                    result = [{"id": jid, "request": job["request"]}]
            return self.send(200, {"jobs": result})
        self.send(404, {"error": {"message": "Not found"}})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path not in ("/v1/chat/completions", "/muse/answer"):
            return self.send(404, {"error": {"message": "Not found"}})
        if not self.authorized("user" if path.startswith("/v1/") else "worker"):
            return
        body = self.read_body()
        if body is None:
            return
        if path == "/muse/answer":
            with LOCK:
                job = JOBS.get(body.get("id", "")) if isinstance(body.get("id"), str) else None
                if job is None or job["deadline"] <= time.monotonic():
                    return self.send(404, {"error": {"message": "Job expired or unknown"}})
                if job["answer"] is not None:
                    return self.send(409, {"error": {"message": "Job already answered"}})
                message = body.get("message")
                if not valid_answer(message, job["request"]):
                    return self.send(400, {"error": {"message": "Invalid assistant message"}})
                job["answer"] = message
                job["event"].set()
            return self.send(200, {"ok": True})
        if body.get("model") != MODEL:
            return self.send(400, {"error": {"message": "Use model muse-bridge"}})
        if body.get("stream"):
            return self.send(400, {"error": {"message": "Prototype requires stream=false"}})
        messages = body.get("messages")
        if not isinstance(messages, list) or not messages or len(messages) > 100:
            return self.send(400, {"error": {"message": "Invalid messages"}})
        if not all(isinstance(m, dict) and m.get("role") in
                   ("system", "developer", "user", "assistant", "tool") for m in messages):
            return self.send(400, {"error": {"message": "Invalid message role"}})
        if "tools" in body and not isinstance(body["tools"], list):
            return self.send(400, {"error": {"message": "Invalid tools"}})
        jid = uuid.uuid4().hex
        job = {"request": body, "event": threading.Event(), "answer": None,
               "deadline": time.monotonic() + WAIT, "lease": 0}
        with LOCK:
            if JOBS:
                return self.send(429, {"error": {"message": "One request at a time during pilot"}})
            JOBS[jid] = job
        try:
            completed = job["event"].wait(WAIT)
            if not completed:
                return self.send(504, {"error": {"message": "Muse worker did not answer"}})
            message = job["answer"]
            self.send(200, {"id": "chatcmpl-" + jid, "object": "chat.completion",
                "created": int(time.time()), "model": MODEL,
                "choices": [{"index": 0, "message": message,
                             "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}]})
        finally:
            with LOCK:
                JOBS.pop(jid, None)

def main():
    global CONFIG
    path = os.environ.get("MUSE_BRIDGE_CONFIG", "/etc/muse-bridge/keys.json")
    with open(path, encoding="utf-8") as handle:
        CONFIG = json.load(handle)
    if (not CONFIG.get("user_key") or not CONFIG.get("worker_key")
            or CONFIG["user_key"] == CONFIG["worker_key"]):
        raise RuntimeError("Separate user and worker keys are required")
    server = ThreadingHTTPServer(("127.0.0.1", 8765), Handler)
    server.daemon_threads = True
    print("Bridge listening on 127.0.0.1:8765; Muse worker not verified", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
