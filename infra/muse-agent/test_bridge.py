import concurrent.futures
import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("bridge", Path(__file__).with_name("bridge.py"))
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bridge.CONFIG = {"user_key": "test-user", "worker_key": "test-worker"}
        bridge.WAIT = 1
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
        cls.server.daemon_threads = True
        cls.url = "http://127.0.0.1:" + str(cls.server.server_address[1])
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path, key=None, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        req = urllib.request.Request(self.url + path, data=data, headers=headers)
        try:
            response = urllib.request.urlopen(req, timeout=4)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def completion(self, **extra):
        payload = {"model": "muse-bridge", "messages": [{"role": "user", "content": "test"}]}
        payload.update(extra)
        return self.request("/v1/chat/completions", "test-user", payload)

    def wait_job(self):
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            status, data = self.request("/muse/pending", "test-worker")
            self.assertEqual(status, 200)
            if data["jobs"]:
                return data["jobs"][0]
            time.sleep(0.01)
        self.fail("No job queued")

    def test_health_does_not_claim_muse_connection(self):
        status, data = self.request("/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["muse_connection"], "unverified")

    def test_roles_are_separate(self):
        self.assertEqual(self.request("/v1/models")[0], 401)
        self.assertEqual(self.request("/v1/models", "test-worker")[0], 401)
        self.assertEqual(self.request("/muse/pending", "test-user")[0], 401)
        self.assertEqual(self.request("/v1/models", "test-user")[0], 200)

    def test_text_requires_worker_and_limits_concurrency(self):
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(self.completion, max_tokens=1024,
                                  messages=[{"role": "user", "content": "hi"}])
            job = self.wait_job()
            self.assertFalse(pending.done())  # no fabricated dashboard completion
            self.assertEqual(self.completion()[0], 429)
            reply = {"id": job["id"], "message": {"role": "assistant", "content": "real worker answer"}}
            self.assertEqual(self.request("/muse/answer", "test-user", reply)[0], 401)
            self.assertEqual(self.request("/muse/answer", "test-worker", reply)[0], 200)
            status, response = pending.result()
            self.assertEqual(status, 200)
            self.assertEqual(response["choices"][0]["message"]["content"], "real worker answer")
            self.assertNotIn("usage", response)  # actual billing unknown

    def test_tool_call_is_preserved_and_unknown_tool_rejected(self):
        tools = [{"type": "function", "function": {"name": "read_file", "parameters": {"type": "object"}}}]
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(self.completion, tools=tools)
            job = self.wait_job()
            self.assertEqual(job["request"]["tools"], tools)
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_one", "type": "function",
                 "function": {"name": "delete_file", "arguments": "{}"}}]}
            reply = {"id": job["id"], "message": message}
            self.assertEqual(self.request("/muse/answer", "test-worker", reply)[0], 400)
            message["tool_calls"][0]["function"]["name"] = "read_file"
            self.assertEqual(self.request("/muse/answer", "test-worker", reply)[0], 200)
            status, response = pending.result()
            self.assertEqual(status, 200)
            self.assertEqual(response["choices"][0]["message"], message)
            self.assertEqual(response["choices"][0]["finish_reason"], "tool_calls")

    def test_timeout_removes_job_and_rejects_late_answer(self):
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(self.completion)
            job = self.wait_job()
            self.assertEqual(pending.result()[0], 504)
            self.assertEqual(self.request("/muse/answer", "test-worker", {
                "id": job["id"], "message": {"role": "assistant", "content": "late"}})[0], 404)
            self.assertFalse(bridge.JOBS)

    def test_invalid_model_stream_and_arguments(self):
        self.assertEqual(self.completion(model="other")[0], 400)
        self.assertEqual(self.completion(stream=True)[0], 400)
        self.assertEqual(self.completion(messages=[])[0], 400)
        self.assertFalse(bridge.valid_answer({"role": "assistant", "content": None}, {}))

if __name__ == "__main__":
    unittest.main()
