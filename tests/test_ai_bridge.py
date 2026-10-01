import base64
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from study_app import ai_bridge as bridge


class Response(io.BytesIO):
    def __init__(self, data, headers=None):
        super().__init__(data if isinstance(data, bytes) else json.dumps(data).encode())
        self.headers = headers or {}


class AIConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.connection = bridge.AIConnection(Path(self.temp.name))

    def save(self, **fields):
        settings = self.connection.configure({"action": "save", "name": "我的服务",
            "protocol": "openai-chat", "base_url": "https://example.com/v1",
            "model": "model-a", "api_key": "test-private-key", **fields})
        return settings["profiles"][-1]["id"]

    def select(self, **fields):
        profile_id = self.save(**fields)
        self.connection.configure({"action": "select", "id": profile_id})
        return profile_id

    def network(self, response, callback=None):
        class Opener:
            def open(self, request, timeout):
                if callback:
                    callback(request, timeout)
                return Response(response)
        return patch.object(bridge, "build_opener", return_value=Opener())

    def test_profiles_persist_without_exposing_keys(self):
        profile_id = self.save()
        settings = bridge.AIConnection(Path(self.temp.name)).settings()
        self.assertEqual(settings["mode"], "codex")
        self.assertEqual(settings["active_profile_id"], "")
        self.assertEqual(settings["profiles"][0]["id"], profile_id)
        self.assertTrue(settings["profiles"][0]["has_api_key"])
        self.assertNotIn("api_key", settings["profiles"][0])
        self.assertNotIn("test-private-key", json.dumps(settings))
        self.assertEqual(json.loads(self.connection.path.read_text(encoding="utf-8"))["profiles"][0]["api_key"], "test-private-key")
        self.assertFalse(list(Path(self.temp.name).glob("*.tmp")))

    def test_blank_or_omitted_key_preserves_saved_key(self):
        profile_id = self.select()
        for fields in ({}, {"api_key": "   "}):
            self.connection.configure({"action": "save", "id": profile_id, "model": "model-b", **fields})
            self.assertEqual(self.connection.settings()["active_profile_id"], profile_id)
            self.assertEqual(json.loads(self.connection.path.read_text(encoding="utf-8"))["profiles"][0]["api_key"], "test-private-key")
        self.connection.configure({"action": "save", "id": profile_id, "api_key": "replacement-key"})
        self.assertEqual(json.loads(self.connection.path.read_text(encoding="utf-8"))["profiles"][0]["api_key"], "replacement-key")

    def test_configuration_validation_does_not_overwrite_state(self):
        self.save()
        previous = self.connection.path.read_bytes()
        invalid = ({"api_key": ""}, {"api_key": "has\nnewline"}, {"model": ""},
                   {"protocol": "unknown"}, {"name": ""}, {"protocol": []},
                   {"id": "missing"}, {"api_key": "中文"})
        for fields in invalid:
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.save(**fields)
            self.assertEqual(self.connection.path.read_bytes(), previous)
        with self.assertRaises(ValueError):
            self.connection.configure({"action": "mode", "mode": "api"})
        with self.assertRaises(ValueError):
            self.connection.configure({"action": "mode", "mode": []})

    def test_urls_require_secure_transport_and_plain_endpoint(self):
        invalid = ("", "file:///tmp/key", "ftp://example.com", "http://example.com",
                   "https://secret@example.com/v1", "https://user:password@example.com/v1",
                   "https://example.com/?key=secret", "https://example.com/#key",
                   "https://example.com/?", "https://example.com/#", "https://example.com:abc",
                   "https://example.com:0", "https://example.com:99999", "https://exa mple.com",
                   "http://127.0.0.1.evil.com", "https://example.com\\@evil.com", "https://")
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.save(base_url=url)
        for url in ("http://localhost:1234", "http://127.0.0.1:1234/v1/", "http://[::1]:1234", "https://example.com/api/v1"):
            with self.subTest(url=url):
                self.save(base_url=url)

    def test_mode_switch_and_active_profile_deletion(self):
        first = self.select()
        second = self.save(name="第二个")
        self.assertEqual(self.connection.settings()["active_profile_id"], first)
        self.connection.configure({"action": "mode", "mode": "codex"})
        self.assertEqual(self.connection.settings()["active_profile_id"], first)
        self.connection.configure({"action": "mode", "mode": "api"})
        self.connection.configure({"action": "delete", "id": second})
        self.assertEqual(self.connection.settings()["mode"], "api")
        self.save(name="保留的配置")
        self.connection.configure({"action": "delete", "id": first})
        self.assertEqual(self.connection.settings()["mode"], "codex")
        self.assertEqual(self.connection.settings()["active_profile_id"], "")
        self.assertEqual(len(self.connection.settings()["profiles"]), 1)

    def test_atomic_write_failure_preserves_previous_settings(self):
        self.save()
        previous = self.connection.path.read_bytes()
        with patch.object(bridge.os, "replace", side_effect=OSError("private-path")):
            with self.assertRaisesRegex(RuntimeError, "无法保存"):
                self.save(name="新连接")
        self.assertEqual(self.connection.path.read_bytes(), previous)
        self.assertFalse(list(Path(self.temp.name).glob("*.tmp")))

    def test_multiple_instances_serialize_profile_writes(self):
        def save(index):
            bridge.AIConnection(Path(self.temp.name)).configure({"action": "save", "name": str(index),
                "protocol": "openai-chat", "base_url": "https://example.com/v1",
                "model": "a", "api_key": "private-key"})
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(executor.map(save, range(10)))
        self.assertEqual(len(self.connection.settings()["profiles"]), 10)

    def test_corrupt_config_returns_a_secret_free_error(self):
        self.connection.path.write_text('{"api_key": "private-key", malformed', encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "无法读取") as error:
            self.connection.settings()
        self.assertNotIn("private-key", str(error.exception))

    def test_codex_remains_default_and_preserves_status_version(self):
        status = {"available": True, "authenticated": False, "version": "codex 1.0", "detail": "请登录"}
        with patch.object(bridge.codex_bridge, "get_status", return_value=status), patch.object(bridge.codex_bridge, "generate", side_effect=lambda prompt: "CLI 回答") as generate:
            self.assertEqual(self.connection.status()["version"], "codex 1.0")
            self.assertFalse(self.connection.status()["authenticated"])
            self.assertEqual(self.connection.generate("问题"), "CLI 回答")
            generate.assert_called_once_with("问题")
        with patch.object(bridge.codex_bridge, "generate", return_value="image answer") as generate:
            self.connection.generate("图片", image_path="one.png", image_paths=["two.jpg"])
            generate.assert_called_once_with("图片", image_path="one.png", image_paths=["two.jpg"])

    def test_api_status_only_claims_key_configuration(self):
        self.select()
        with patch.object(bridge.codex_bridge, "get_status", side_effect=AssertionError("must not use CLI")):
            status = self.connection.status()
        self.assertEqual(status["mode"], "api")
        self.assertEqual(status["model"], "model-a")
        self.assertIn("测试连接", status["detail"])
        self.assertNotIn("test-private-key", json.dumps(status))

    def test_endpoint_normalization_and_models_sibling(self):
        cases = (("https://example.com", "openai-chat", "https://example.com/v1/chat/completions"),
                 ("https://example.com/v1", "openai-responses", "https://example.com/v1/responses"),
                 ("https://example.com/api/v1/chat/completions", "openai-chat", "https://example.com/api/v1/chat/completions"),
                 ("https://example.com/v1/chat/completions", "openai-responses", "https://example.com/v1/responses"),
                 ("https://example.com", "anthropic", "https://example.com/v1/messages"))
        for base, protocol, expected in cases:
            with self.subTest(base=base, protocol=protocol):
                self.assertEqual(bridge._endpoint(base, protocol), expected)
                self.assertEqual(bridge._endpoint(expected, protocol, models=True), expected.rsplit("/chat/completions", 1)[0] + "/models" if protocol == "openai-chat" else expected.rsplit("/", 1)[0] + "/models")

    def test_chat_payload_and_key_redaction(self):
        self.select(base_url="https://example.com")
        captured = {}
        def inspect(request, timeout):
            captured["payload"] = json.loads(request.data)
            self.assertEqual(request.full_url, "https://example.com/v1/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-private-key")
            self.assertEqual(timeout, 180)
        with self.network({"choices": [{"message": {"content": "解答 test-private-key"}}]}, inspect):
            self.assertEqual(self.connection.generate("解释导数"), "解答 [已隐藏]")
        self.assertEqual(captured["payload"]["messages"][1], {"role": "user", "content": "解释导数"})
        self.assertEqual(captured["payload"]["model"], "model-a")
        self.assertNotIn("tools", captured["payload"])

    def test_image_formats_for_all_three_protocols(self):
        image = Path(self.temp.name) / "one.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\nimage-data")
        encoded = base64.b64encode(image.read_bytes()).decode()
        for protocol in bridge.PROTOCOLS:
            with self.subTest(protocol=protocol):
                self.select(protocol=protocol)
                captured = {}
                def inspect(request, timeout):
                    captured.update(json.loads(request.data))
                    if protocol == "anthropic":
                        self.assertEqual(request.get_header("X-api-key"), "test-private-key")
                        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
                        self.assertIsNone(request.get_header("Authorization"))
                response = {"content": [{"type": "text", "text": "图像解答"}]} if protocol == "anthropic" else (
                    {"output": [{"type": "reasoning", "content": []}, {"type": "message", "content": [{"type": "output_text", "text": "图像解答"}]}]}
                    if protocol == "openai-responses" else {"choices": [{"message": {"content": "图像解答"}}]})
                with self.network(response, inspect):
                    self.assertEqual(self.connection.generate("解释图像", image_path=str(image), image_paths=[str(image)]), "图像解答")
                if protocol == "anthropic":
                    source = captured["messages"][0]["content"][0]["source"]
                    self.assertEqual(source, {"type": "base64", "media_type": "image/png", "data": encoded})
                    self.assertEqual(len(captured["messages"][0]["content"]), 2)
                elif protocol == "openai-responses":
                    self.assertEqual(captured["input"][0]["content"][1], {"type": "input_image", "image_url": "data:image/png;base64," + encoded})
                    self.assertFalse(captured["store"])
                else:
                    self.assertEqual(captured["messages"][1]["content"][1], {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded}})

    def test_empty_malformed_and_error_responses_are_not_exposed(self):
        self.select()
        invalid = (b"<html>test-private-key</html>", [], {"error": {"message": "test-private-key"}},
                   {"choices": [{"message": {"content": None}}]}, {"choices": "invalid"},
                   {"choices": [{"message": "invalid"}]})
        for response in invalid:
            with self.subTest(response=response), self.network(response):
                with self.assertRaises(RuntimeError) as error:
                    self.connection.generate("问题")
                self.assertNotIn("test-private-key", str(error.exception))

    def test_invalid_prompt_or_image_fails_before_network(self):
        self.select()
        invalid_image = Path(self.temp.name) / "fake.png"
        invalid_image.write_bytes(b"not an image")
        with patch.object(bridge, "_request_json", side_effect=AssertionError("network must not run")):
            for prompt in ("", " ", "a" * 100001, None):
                with self.subTest(prompt=str(prompt)[:20]), self.assertRaises(ValueError):
                    self.connection.generate(prompt)
            with self.assertRaises(ValueError):
                self.connection.generate("问题", image_path=str(invalid_image))
            with self.assertRaises(ValueError):
                self.connection.generate("问题", image_path=str(Path(self.temp.name) / "missing.png"))

    def test_http_errors_are_actionable_and_do_not_read_provider_body(self):
        self.select()
        for code, expected in ((401, "API Key"), (403, "权限"), (404, "地址"), (429, "额度"), (302, "重定向"), (500, "HTTP 500")):
            body = io.BytesIO(b"test-private-key provider diagnostic")
            error = HTTPError("https://example.com/test-private-key", code, "test-private-key", {}, body)
            with self.subTest(code=code), patch.object(bridge, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesRegex(RuntimeError, expected) as raised:
                    self.connection.generate("问题")
                self.assertNotIn("test-private-key", str(raised.exception))
                self.assertTrue(body.closed)

    def test_network_errors_are_sanitized(self):
        self.select()
        for error in (URLError("test-private-key"), TimeoutError("test-private-key"), OSError("test-private-key")):
            with self.subTest(error=type(error)), patch.object(bridge, "build_opener") as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(RuntimeError) as raised:
                    self.connection.generate("问题")
                self.assertNotIn("test-private-key", str(raised.exception))

    def test_total_wait_is_bounded_even_if_transport_stalls(self):
        release = threading.Event()
        with patch.object(bridge, "TIMEOUT_SECONDS", 0.02), patch.object(bridge, "_perform_request", side_effect=lambda request: release.wait(1)):
            start = time.monotonic()
            with self.assertRaisesRegex(RuntimeError, "3 分钟"):
                bridge._request_json(Request("https://example.com"))
            self.assertLess(time.monotonic() - start, 0.5)
            release.set()

    def test_oversized_response_is_rejected(self):
        self.select()
        for response in (Response(b"{}", {"Content-Length": "2000001"}), Response(b"a" * 2000001)):
            with self.subTest(headers=response.headers), patch.object(bridge, "build_opener") as opener:
                opener.return_value.open.return_value = response
                with self.assertRaisesRegex(RuntimeError, "过大"):
                    self.connection.generate("问题")

    def test_redirect_never_forwards_api_key(self):
        paths = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                paths.append(self.path)
                self.send_response(307)
                self.send_header("Location", "/stolen")
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            self.select(base_url=f"http://127.0.0.1:{server.server_port}/v1")
            with self.assertRaisesRegex(RuntimeError, "重定向"):
                self.connection.generate("问题")
            self.assertEqual(paths, ["/v1/chat/completions"])
        finally:
            server.shutdown()
            server.server_close()
            worker.join()

    def test_connection_test_uses_saved_profile_without_switching(self):
        first = self.select()
        second = self.save(name="第二个", model="model-b")
        captured = {}
        with self.network({"choices": [{"message": {"content": "成功"}}]}, lambda request, timeout: captured.update(json.loads(request.data))):
            result = self.connection.test(second)
        self.assertTrue(result["ok"])
        self.assertEqual(result["model"], "model-b")
        self.assertEqual(captured["model"], "model-b")
        self.assertEqual(self.connection.settings()["active_profile_id"], first)
        self.assertNotIn("test-private-key", json.dumps(result))

    def test_models_enumeration_normalizes_endpoint_sanitizes_and_deduplicates(self):
        profile_id = self.save(base_url="https://example.com/v1/chat/completions")
        def inspect(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertEqual(request.full_url, "https://example.com/v1/models")
        with self.network({"data": [{"id": "z"}, {"id": "a", "display_name": "Model A"}, {"id": "z"},
                                    {"id": "test-private-key"}, {"id": "invalid\nmodel"}, {"id": 123},
                                    {"id": "b", "name": "test-private-key"}]}, inspect):
            result = self.connection.models(profile_id)
        self.assertEqual(result["models"], [{"id": "a", "name": "Model A"}, {"id": "b", "name": "[已隐藏]"}, {"id": "z", "name": "z"}])
        self.assertEqual(self.connection.settings()["mode"], "codex")

    def test_anthropic_models_and_manual_entry_fallback(self):
        profile_id = self.save(protocol="anthropic", base_url="https://example.com/v1/messages")
        def inspect(request, timeout):
            self.assertEqual(request.full_url, "https://example.com/v1/models")
            self.assertEqual(request.get_header("X-api-key"), "test-private-key")
        with self.network({"data": [{"id": "claude-example", "display_name": "Claude Example"}]}, inspect):
            self.assertEqual(self.connection.models(profile_id)["models"][0]["name"], "Claude Example")
        with self.network({"unsupported": True}):
            with self.assertRaisesRegex(RuntimeError, "手动填写"):
                self.connection.models(profile_id)
        with self.assertRaises(ValueError):
            self.connection.models("missing")

    def test_new_connection_can_discover_models_before_save(self):
        captured = {}
        def inspect(request, timeout):
            captured["url"] = request.full_url
            captured["key"] = request.get_header("Authorization")
        with self.network({"data": [{"id": "discovered", "name": "new-private-key"}]}, inspect):
            result = self.connection.models_for_config({"protocol": "openai-chat",
                "base_url": "https://new.example.com/v1", "api_key": "new-private-key"})
        self.assertEqual(result, {"models": [{"id": "discovered", "name": "[已隐藏]"}]})
        self.assertEqual(captured, {"url": "https://new.example.com/v1/models", "key": "Bearer new-private-key"})
        self.assertFalse(self.connection.path.exists())
        self.assertEqual(self.connection.settings()["profiles"], [])

    def test_discovery_can_reuse_key_only_with_explicit_saved_id(self):
        profile_id = self.select()
        previous = self.connection.path.read_bytes()
        def inspect(request, timeout):
            self.assertEqual(request.full_url, "https://changed.example.com/v1/models")
            self.assertEqual(request.get_header("X-api-key"), "test-private-key")
        with self.network({"data": [{"id": "claude-example"}]}, inspect):
            self.connection.models_for_config({"id": profile_id, "protocol": "anthropic",
                "base_url": "https://changed.example.com/v1/messages", "api_key": ""})
        self.assertEqual(self.connection.path.read_bytes(), previous)
        with self.assertRaises(ValueError):
            self.connection.models_for_config({"protocol": "openai-chat", "base_url": "https://example.com/v1"})
        with self.assertRaises(ValueError):
            self.connection.models_for_config({"id": "missing", "protocol": "openai-chat",
                "base_url": "https://example.com/v1", "api_key": "new-key"})

    def test_model_names_redact_before_truncation(self):
        long_key = "private-key-" + "x" * 250
        profile_id = self.save(api_key=long_key)
        with self.network({"data": [{"id": "model", "display_name": "a" * 150 + long_key + "tail"}]}):
            name = self.connection.models(profile_id)["models"][0]["name"]
        self.assertEqual(name, "a" * 150 + "[已隐藏]tail")
        self.assertNotIn("private-key-", name)


if __name__ == "__main__":
    unittest.main()
