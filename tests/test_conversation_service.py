import http.client
import json
import runpy
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APPLIANCE = ROOT / "image-builder/sovereign/appliance"
LIB = APPLIANCE / "lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))
CONVERSATION_SERVICE = APPLIANCE / "bin/sovereign-conversation"
SYSTEMD_SERVICE = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
    / "etc/systemd/system/sovereign-conversation.service"
)
SYSUSERS = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
    / "usr/lib/sysusers.d/sovereign-pihole-secrets.conf"
)

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_homeassistant as homeassistant  # noqa: E402
import sovereign_system as system  # noqa: E402
import sovereign_websearch as websearch  # noqa: E402


def json_response(payload):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


def chat_completion(content=None, tool_calls=None):
    message = {}
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    if content is not None:
        message["content"] = content
    return json_response({"choices": [{"message": message}]})


def tool_call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def healthy_payload():
    return {
        "status": "healthy",
        "checked_at": "2026-08-09T15:00:00Z",
        "system": {
            "name": "Sovereign OS",
            "version": "0.1.0-proof.3",
            "model": "Raspberry Pi 5 Model B Rev 1.1",
            "uptime_seconds": 123456,
            "memory": {"total_bytes": 16000000000, "available_bytes": 12000000000, "used_percent": 25.0},
            "data_storage": {"total_bytes": 500000000000, "available_bytes": 400000000000, "used_percent": 20.0},
            "temperature_celsius": 48.5,
            "network": [{"name": "eth0", "state": "up", "addresses": ["192.168.1.42"]}],
        },
        "checks": {
            "storage": {"status": "healthy", "summary": "Persistent storage available"},
            "dns": {"status": "healthy", "summary": "Resolving normally"},
            "update": {"status": "healthy", "summary": "Latest update committed"},
            "pihole": {"status": "healthy", "summary": "Pi-hole is available"},
            "local_access": {"status": "healthy", "summary": "Console is reachable"},
        },
    }


def dispatch_urlopen(rules):
    # rules: list of (url_substring, response_or_exception) consumed in
    # order, one per matching call -- mirrors that a single turn can call
    # the same path (e.g. /v1/chat/completions) more than once across
    # propose/execute rounds, each needing its own canned response.
    remaining = list(rules)

    def _urlopen(request, timeout=None):
        url = request.full_url
        for index, (substring, response) in enumerate(remaining):
            if substring in url:
                del remaining[index]
                if isinstance(response, BaseException):
                    raise response
                return response
        raise AssertionError(f"unexpected urlopen call: {url} (remaining rules: {remaining})")

    return _urlopen


def auth_ok():
    return ("/api/v1/auth/verify-mutating", mock.MagicMock())


class LiveConversationServer:
    def __init__(
        self, audit_log_path, policy_path=None,
        home_assistant_config_path=None, home_assistant_token_path=None,
    ):
        environment = {"SOVEREIGN_CONVERSATION_AUDIT_LOG_PATH": str(audit_log_path)}
        if policy_path is not None:
            environment["SOVEREIGN_CONVERSATION_POLICY_PATH"] = str(policy_path)
        if home_assistant_config_path is not None:
            environment["SOVEREIGN_HOME_ASSISTANT_CONFIG_PATH"] = str(home_assistant_config_path)
        if home_assistant_token_path is not None:
            environment["SOVEREIGN_HOME_ASSISTANT_TOKEN_PATH"] = str(home_assistant_token_path)
        with mock.patch.dict(__import__("os").environ, environment):
            self.module = runpy.run_path(str(CONVERSATION_SERVICE))
        from http.server import ThreadingHTTPServer

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.module["ConversationHandler"])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server.server_port

    def connection(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


class ConversationServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audit_path = Path(self.temporary.name) / "audit.jsonl"
        self.live = LiveConversationServer(self.audit_path)
        self.addCleanup(self.live.stop)

    def _post_message(self, payload, headers=None):
        connection = self.live.connection()
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload)
        else:
            body = payload
        connection.request(
            "POST",
            "/api/v1/conversation/message",
            body=body,
            headers=headers or {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_health_endpoint_reports_provider_health(self):
        # Deliberately unauthenticated -- no auth_ok() rule needed here.
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([("/health", json_response({"status": "ok"}))])
            connection = self.live.connection()
            connection.request("GET", "/api/v1/conversation/health")
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        self.assertEqual(200, response.status)
        self.assertTrue(body["healthy"])

    def test_plain_message_returns_narration_with_no_capability_events(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", chat_completion(content="Hello there."))]
            )
            response, body = self._post_message({"message": "hi"})
        self.assertEqual(200, response.status)
        self.assertEqual("Hello there.", body["text"])
        self.assertEqual([], body["capability_events"])

    def test_missing_message_is_rejected(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post_message({})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_non_list_messages_history_is_rejected(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post_message({"message": "hi", "messages": "not a list"})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_malformed_json_body_is_rejected(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post_message("not json")
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_capability_proposal_executes_against_the_real_registry_and_narrates(self):
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "system.health", {})])
        narration = chat_completion(content="The system is healthy.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [
                    auth_ok(),
                    ("/v1/chat/completions", proposal),
                    (system.HEALTH_BASE_URL, json_response(healthy_payload())),
                    ("/v1/chat/completions", narration),
                ]
            )
            response, body = self._post_message({"message": "how's the system doing?"})
        self.assertEqual(200, response.status)
        self.assertEqual("The system is healthy.", body["text"])
        self.assertEqual(
            [{"name": "system.health", "outcome": "executed"}], body["capability_events"]
        )
        self.assertTrue(self.audit_path.exists())
        events = [json.loads(line) for line in self.audit_path.read_text().splitlines()]
        self.assertEqual(1, len(events))
        self.assertEqual("system.health", events[0]["capability"])
        self.assertEqual("executed", events[0]["outcome"])

    def test_unreachable_provider_reports_502(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", urllib.error.URLError("connection refused"))]
            )
            response, body = self._post_message({"message": "hi"})
        self.assertEqual(502, response.status)
        self.assertEqual("PROVIDER_UNAVAILABLE", body["error"]["code"])

    def test_message_without_a_session_is_rejected_as_not_authenticated(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 401, "unauthorized", {}, None))]
            )
            response, body = self._post_message({"message": "hi"})
        self.assertEqual(401, response.status)
        self.assertEqual("NOT_AUTHENTICATED", body["error"]["code"])

    def test_message_with_a_session_but_no_csrf_token_is_rejected(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 403, "forbidden", {}, None))]
            )
            response, body = self._post_message(
                {"message": "hi"},
                headers={
                    "Content-Type": "application/json",
                    "Cookie": "sovereign_console_session=abc123",
                },
            )
        self.assertEqual(403, response.status)
        self.assertEqual("CSRF_MISMATCH", body["error"]["code"])

    def test_message_when_auth_service_is_unreachable_reports_503(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.URLError("connection refused"))]
            )
            response, body = self._post_message({"message": "hi"})
        self.assertEqual(503, response.status)
        self.assertEqual("AUTH_SERVICE_UNAVAILABLE", body["error"]["code"])

    def test_message_forwards_the_caller_s_cookie_and_csrf_header_to_console_auth(self):
        captured = {}

        def capture(request, timeout=None):
            if "/api/v1/auth/verify-mutating" in request.full_url:
                captured["cookie"] = request.get_header("Cookie")
                captured["csrf"] = request.get_header("X-csrf-token")
                return mock.MagicMock()
            return chat_completion(content="hi there")

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = capture
            self._post_message(
                {"message": "hi"},
                headers={
                    "Content-Type": "application/json",
                    "Cookie": "sovereign_console_session=abc123",
                    "X-CSRF-Token": "the-real-token",
                },
            )
        self.assertEqual("sovereign_console_session=abc123", captured["cookie"])
        self.assertEqual("the-real-token", captured["csrf"])


class ConfirmationWireFormatTests(unittest.TestCase):
    # RFC-0017: the confirmation pause/resume wire format --
    # pending_confirmation on the way out, {"confirmation": {"token",
    # "approve"}} on the way back in -- and the external_enabled policy
    # gate that runs before it.
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audit_path = Path(self.temporary.name) / "audit.jsonl"
        self.policy_path = Path(self.temporary.name) / "policy.json"

    def enable_web_search(self):
        self.policy_path.write_text(json.dumps({"web_search_enabled": True}))

    def start_server(self):
        self.live = LiveConversationServer(self.audit_path, policy_path=self.policy_path)
        self.addCleanup(self.live.stop)

    def _post(self, payload, headers=None):
        connection = self.live.connection()
        connection.request(
            "POST", "/api/v1/conversation/message",
            body=json.dumps(payload),
            headers=headers or {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_disabled_by_default_rejects_without_ever_prompting(self):
        # No policy file at all -- must fail safe to disabled, not to
        # some other default.
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "raspberry pi"})])
        narration = chat_completion(content="Web search is disabled.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", proposal), ("/v1/chat/completions", narration)]
            )
            response, body = self._post({"message": "search for raspberry pi"})
        self.assertEqual(200, response.status)
        self.assertNotIn("pending_confirmation", body)
        self.assertEqual(
            [{"name": "web.search", "outcome": "rejected", "code": "CAPABILITY_DISABLED"}],
            body["capability_events"],
        )

    def test_enabled_proposal_pauses_for_confirmation_disclosing_the_query(self):
        self.enable_web_search()
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "raspberry pi"})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            response, body = self._post({"message": "search for raspberry pi"})
        self.assertEqual(200, response.status)
        self.assertEqual([], body["capability_events"])
        self.assertEqual("web.search", body["pending_confirmation"]["capability"])
        self.assertEqual({"query": "raspberry pi"}, body["pending_confirmation"]["arguments"])
        self.assertIn("token", body["pending_confirmation"])

    def test_approving_executes_the_real_capability_and_narrates(self):
        self.enable_web_search()
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "raspberry pi"})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            _, paused = self._post({"message": "search for raspberry pi"})
        token = paused["pending_confirmation"]["token"]

        searxng_payload = {
            "query": "raspberry pi",
            "results": [{"title": "Raspberry Pi", "url": "https://www.raspberrypi.com/", "content": "official site"}],
        }
        narration = chat_completion(content="Here's what I found.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [
                    auth_ok(),
                    (websearch.SEARXNG_BASE_URL, json_response(searxng_payload)),
                    ("/v1/chat/completions", narration),
                ]
            )
            response, body = self._post({"confirmation": {"token": token, "approve": True}})
        self.assertEqual(200, response.status)
        self.assertEqual("Here's what I found.", body["text"])
        self.assertEqual([{"name": "web.search", "outcome": "executed"}], body["capability_events"])
        self.assertNotIn("pending_confirmation", body)

    def test_denying_records_a_denial_without_calling_searxng(self):
        self.enable_web_search()
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "raspberry pi"})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            _, paused = self._post({"message": "search for raspberry pi"})
        token = paused["pending_confirmation"]["token"]

        narration = chat_completion(content="Okay, not searching.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            # No SearXNG rule registered at all -- dispatch_urlopen raises
            # AssertionError on any unexpected call, so this also proves
            # SearXNG is never contacted on a denial.
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", narration)])
            response, body = self._post({"confirmation": {"token": token, "approve": False}})
        self.assertEqual(200, response.status)
        self.assertEqual([{"name": "web.search", "outcome": "denied"}], body["capability_events"])

    def test_resuming_with_an_unknown_token_is_a_400(self):
        self.start_server()
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post({"confirmation": {"token": "not-a-real-token", "approve": True}})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_CONFIRMATION", body["error"]["code"])

    def test_resuming_the_same_token_twice_is_rejected_the_second_time(self):
        self.enable_web_search()
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "x"})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            _, paused = self._post({"message": "x"})
        token = paused["pending_confirmation"]["token"]

        narration = chat_completion(content="done")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", narration)])
            self._post({"confirmation": {"token": token, "approve": False}})

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post({"confirmation": {"token": token, "approve": True}})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_CONFIRMATION", body["error"]["code"])

    def test_confirmation_missing_approve_field_is_rejected(self):
        self.start_server()
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post({"confirmation": {"token": "x"}})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_policy_change_takes_effect_without_a_restart(self):
        # Read fresh per request, not cached at process start.
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "x"})])
        narration = chat_completion(content="disabled")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", proposal), ("/v1/chat/completions", narration)]
            )
            _, before = self._post({"message": "x"})
        self.assertNotIn("pending_confirmation", before)

        self.enable_web_search()
        proposal2 = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "x"})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal2)])
            _, after = self._post({"message": "x"})
        self.assertIn("pending_confirmation", after)


class PolicyEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audit_path = Path(self.temporary.name) / "audit.jsonl"
        self.policy_path = Path(self.temporary.name) / "capabilities" / "policy.json"
        self.live = LiveConversationServer(self.audit_path, policy_path=self.policy_path)
        self.addCleanup(self.live.stop)

    def _get(self, path, headers=None):
        connection = self.live.connection()
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def _post(self, path, payload, headers=None):
        connection = self.live.connection()
        connection.request(
            "POST", path, body=json.dumps(payload),
            headers=headers or {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_get_requires_authentication(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 401, "unauthorized", {}, None))]
            )
            response, body = self._get("/api/v1/conversation/policy")
        self.assertEqual(401, response.status)
        self.assertEqual("NOT_AUTHENTICATED", body["error"]["code"])

    def test_get_reflects_the_real_default_disabled(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._get("/api/v1/conversation/policy")
        self.assertEqual(200, response.status)
        self.assertEqual(False, body["web_search_enabled"])

    def test_post_requires_authentication(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 403, "forbidden", {}, None))]
            )
            response, body = self._post("/api/v1/conversation/policy", {"web_search_enabled": True})
        self.assertEqual(403, response.status)
        self.assertEqual("CSRF_MISMATCH", body["error"]["code"])

    def test_post_persists_and_get_reflects_it(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post("/api/v1/conversation/policy", {"web_search_enabled": True})
        self.assertEqual(200, response.status)
        self.assertEqual(True, body["web_search_enabled"])

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._get("/api/v1/conversation/policy")
        self.assertEqual(True, body["web_search_enabled"])

        self.assertEqual(
            json.loads(self.policy_path.read_text()), {"web_search_enabled": True}
        )

    def test_post_rejects_a_non_boolean_value(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post("/api/v1/conversation/policy", {"web_search_enabled": "yes"})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_disabling_after_enabling_takes_effect_on_the_next_message(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            self._post("/api/v1/conversation/policy", {"web_search_enabled": True})

        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "x"})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            connection = self.live.connection()
            connection.request(
                "POST", "/api/v1/conversation/message",
                body=json.dumps({"message": "x"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        self.assertIn("pending_confirmation", body)

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            self._post("/api/v1/conversation/policy", {"web_search_enabled": False})

        proposal2 = chat_completion(tool_calls=[tool_call("call_1_0", "web.search", {"query": "x"})])
        narration = chat_completion(content="disabled now")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", proposal2), ("/v1/chat/completions", narration)]
            )
            connection = self.live.connection()
            connection.request(
                "POST", "/api/v1/conversation/message",
                body=json.dumps({"message": "x"}),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        self.assertNotIn("pending_confirmation", body)
        self.assertEqual(
            [{"name": "web.search", "outcome": "rejected", "code": "CAPABILITY_DISABLED"}],
            body["capability_events"],
        )


class HomeAssistantConfigEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audit_path = Path(self.temporary.name) / "audit.jsonl"
        self.config_path = Path(self.temporary.name) / "capabilities" / "home-assistant.json"
        self.token_path = Path(self.temporary.name) / "secrets" / "home-assistant" / "access-token"
        self.live = LiveConversationServer(
            self.audit_path,
            home_assistant_config_path=self.config_path,
            home_assistant_token_path=self.token_path,
        )
        self.addCleanup(self.live.stop)

    def _get(self, path, headers=None):
        connection = self.live.connection()
        connection.request("GET", path, headers=headers or {})
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def _post(self, path, payload, headers=None):
        connection = self.live.connection()
        connection.request(
            "POST", path, body=json.dumps(payload),
            headers=headers or {"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_get_requires_authentication(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 401, "unauthorized", {}, None))]
            )
            response, body = self._get("/api/v1/conversation/home-assistant")
        self.assertEqual(401, response.status)
        self.assertEqual("NOT_AUTHENTICATED", body["error"]["code"])

    def test_get_reflects_the_real_default_disabled_unconfigured(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._get("/api/v1/conversation/home-assistant")
        self.assertEqual(200, response.status)
        self.assertEqual(
            body,
            {"enabled": False, "base_url": "", "has_access_token": False, "allowlisted_entities": []},
        )

    def test_post_requires_authentication(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 403, "forbidden", {}, None))]
            )
            response, body = self._post(
                "/api/v1/conversation/home-assistant",
                {"enabled": True, "base_url": "http://homeassistant.local:8123", "allowlisted_entities": []},
            )
        self.assertEqual(403, response.status)
        self.assertEqual("CSRF_MISMATCH", body["error"]["code"])

    def test_post_persists_and_get_reflects_it_never_returning_the_token(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post(
                "/api/v1/conversation/home-assistant",
                {
                    "enabled": True,
                    "base_url": "http://homeassistant.local:8123",
                    "allowlisted_entities": ["light.kitchen"],
                    "access_token": "secret-1",
                },
            )
        self.assertEqual(200, response.status)
        self.assertEqual(
            body,
            {
                "enabled": True,
                "base_url": "http://homeassistant.local:8123",
                "has_access_token": True,
                "allowlisted_entities": ["light.kitchen"],
            },
        )
        self.assertNotIn("secret-1", json.dumps(body))

        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._get("/api/v1/conversation/home-assistant")
        self.assertEqual(body["allowlisted_entities"], ["light.kitchen"])
        self.assertEqual(homeassistant.read_token(self.token_path), "secret-1")

    def test_omitted_access_token_leaves_the_stored_token_unchanged(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            self._post(
                "/api/v1/conversation/home-assistant",
                {
                    "enabled": True, "base_url": "http://x:8123",
                    "allowlisted_entities": [], "access_token": "secret-1",
                },
            )
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post(
                "/api/v1/conversation/home-assistant",
                {"enabled": True, "base_url": "http://x:8123", "allowlisted_entities": ["light.kitchen"]},
            )
        self.assertTrue(body["has_access_token"])
        self.assertEqual(homeassistant.read_token(self.token_path), "secret-1")

    def test_post_rejects_a_non_boolean_enabled(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post(
                "/api/v1/conversation/home-assistant",
                {"enabled": "yes", "base_url": "http://x:8123", "allowlisted_entities": []},
            )
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_post_rejects_a_non_http_base_url(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post(
                "/api/v1/conversation/home-assistant",
                {"enabled": True, "base_url": "ftp://x", "allowlisted_entities": []},
            )
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_post_rejects_a_non_list_allowlist(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._post(
                "/api/v1/conversation/home-assistant",
                {"enabled": True, "base_url": "http://x:8123", "allowlisted_entities": "light.kitchen"},
            )
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])


class HomeAssistantEntitiesProxyEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audit_path = Path(self.temporary.name) / "audit.jsonl"
        self.config_path = Path(self.temporary.name) / "capabilities" / "home-assistant.json"
        self.token_path = Path(self.temporary.name) / "secrets" / "home-assistant" / "access-token"
        self.live = LiveConversationServer(
            self.audit_path,
            home_assistant_config_path=self.config_path,
            home_assistant_token_path=self.token_path,
        )
        self.addCleanup(self.live.stop)

    def _get(self, headers=None):
        connection = self.live.connection()
        connection.request("GET", "/api/v1/conversation/home-assistant/entities", headers=headers or {})
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_requires_authentication(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [("/api/v1/auth/verify-mutating", urllib.error.HTTPError("url", 401, "unauthorized", {}, None))]
            )
            response, body = self._get()
        self.assertEqual(401, response.status)

    def test_not_configured_is_a_409(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            response, body = self._get()
        self.assertEqual(409, response.status)
        self.assertEqual("HOME_ASSISTANT_NOT_CONFIGURED", body["error"]["code"])

    def test_returns_the_unfiltered_entity_list_not_just_the_allowlist(self):
        homeassistant.write_config(
            "http://homeassistant.local:8123", ["light.kitchen"], True, access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )
        states_payload = [
            {"entity_id": "light.kitchen", "state": "on", "attributes": {"friendly_name": "Kitchen"}},
            {"entity_id": "lock.front_door", "state": "locked", "attributes": {"friendly_name": "Front Door"}},
        ]
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/api/states", json_response(states_payload))])
            response, body = self._get()
        self.assertEqual(200, response.status)
        entity_ids = {entity["entity_id"] for entity in body["entities"]}
        # Deliberately not filtered to the allowlist -- this is the
        # settings-page proxy a household uses to build the allowlist.
        self.assertEqual(entity_ids, {"light.kitchen", "lock.front_door"})


class HomeAssistantConfirmationWireFormatTests(unittest.TestCase):
    # RFC-0018's own Acceptance Criteria: no new wire-format code path,
    # only a second registration reusing RFC-0017's existing
    # pending_confirmation/confirmation mechanism.
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.audit_path = Path(self.temporary.name) / "audit.jsonl"
        self.config_path = Path(self.temporary.name) / "capabilities" / "home-assistant.json"
        self.token_path = Path(self.temporary.name) / "secrets" / "home-assistant" / "access-token"

    def configure_and_enable(self, allowlist=("light.kitchen",)):
        homeassistant.write_config(
            "http://homeassistant.local:8123", list(allowlist), True, access_token="secret-1",
            path=self.config_path, token_path=self.token_path,
        )

    def start_server(self):
        self.live = LiveConversationServer(
            self.audit_path,
            home_assistant_config_path=self.config_path,
            home_assistant_token_path=self.token_path,
        )
        self.addCleanup(self.live.stop)

    def _post(self, payload):
        connection = self.live.connection()
        connection.request(
            "POST", "/api/v1/conversation/message",
            body=json.dumps(payload), headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_disabled_by_default_rejects_without_ever_prompting(self):
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "home_assistant.list_entities", {})])
        narration = chat_completion(content="Home Assistant is disabled.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", proposal), ("/v1/chat/completions", narration)]
            )
            response, body = self._post({"message": "what lights are on"})
        self.assertEqual(200, response.status)
        self.assertNotIn("pending_confirmation", body)
        self.assertEqual(
            [{"name": "home_assistant.list_entities", "outcome": "rejected", "code": "CAPABILITY_DISABLED"}],
            body["capability_events"],
        )

    def test_enabled_proposal_pauses_for_confirmation(self):
        self.configure_and_enable()
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "home_assistant.list_entities", {})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            response, body = self._post({"message": "what lights are on"})
        self.assertEqual(200, response.status)
        self.assertEqual("home_assistant.list_entities", body["pending_confirmation"]["capability"])
        self.assertIn("token", body["pending_confirmation"])

    def test_approving_executes_the_real_capability_and_narrates(self):
        self.configure_and_enable()
        self.start_server()
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "home_assistant.list_entities", {})])
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok(), ("/v1/chat/completions", proposal)])
            _, paused = self._post({"message": "what lights are on"})
        token = paused["pending_confirmation"]["token"]

        states_payload = [{"entity_id": "light.kitchen", "state": "on", "attributes": {}}]
        narration = chat_completion(content="The kitchen light is on.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/api/states", json_response(states_payload)), ("/v1/chat/completions", narration)]
            )
            response, body = self._post({"confirmation": {"token": token, "approve": True}})
        self.assertEqual(200, response.status)
        self.assertEqual("The kitchen light is on.", body["text"])
        self.assertEqual(
            [{"name": "home_assistant.list_entities", "outcome": "executed"}], body["capability_events"],
        )

    def test_entity_not_allowlisted_is_rejected_before_confirmation(self):
        self.configure_and_enable(allowlist=("light.kitchen",))
        self.start_server()
        proposal = chat_completion(
            tool_calls=[tool_call("call_1_0", "home_assistant.get_history", {"entity_id": "lock.front_door", "period": "day"})]
        )
        narration = chat_completion(content="That entity isn't available.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", proposal), ("/v1/chat/completions", narration)]
            )
            response, body = self._post({"message": "when was the front door unlocked"})
        self.assertEqual(200, response.status)
        self.assertNotIn("pending_confirmation", body)
        self.assertEqual(
            [{"name": "home_assistant.get_history", "outcome": "rejected", "code": "ENTITY_NOT_ALLOWLISTED"}],
            body["capability_events"],
        )

    def test_enabling_web_search_alone_does_not_enable_home_assistant(self):
        # Cross-feature independence, proven at the HTTP layer too, not
        # just the executor unit tests.
        self.start_server()
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen([auth_ok()])
            connection = self.live.connection()
            connection.request(
                "POST", "/api/v1/conversation/policy",
                body=json.dumps({"web_search_enabled": True}),
                headers={"Content-Type": "application/json"},
            )
            connection.getresponse().read()
            connection.close()

        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "home_assistant.list_entities", {})])
        narration = chat_completion(content="Home Assistant is disabled.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [auth_ok(), ("/v1/chat/completions", proposal), ("/v1/chat/completions", narration)]
            )
            response, body = self._post({"message": "what lights are on"})
        self.assertEqual(
            [{"name": "home_assistant.list_entities", "outcome": "rejected", "code": "CAPABILITY_DISABLED"}],
            body["capability_events"],
        )


class ConversationProvisioningTests(unittest.TestCase):
    def test_systemd_unit_is_hardened_and_grouped(self):
        service = SYSTEMD_SERVICE.read_text()
        self.assertIn("DynamicUser=yes", service)
        self.assertIn("SupplementaryGroups=sovereign-pihole-secrets", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("CapabilityBoundingSet=", service)
        self.assertIn(
            "ExecStart=/opt/sovereign/current/appliance/bin/sovereign-conversation",
            service,
        )
        self.assertIn("After=", service)
        self.assertIn("systemd-sysusers.service", service)
        self.assertIn("ReadWritePaths=/data/sovereign/capabilities", service)
        # RFC-0018: the Home Assistant access token's own writable
        # directory, deliberately separate from
        # /data/sovereign/secrets/pihole-admin-password's own -- a
        # compromised sovereign-conversation.service process must gain no
        # new ability to touch Pi-hole's credential.
        self.assertIn("/data/sovereign/secrets/home-assistant", service)

    def test_group_declared_via_sysusers(self):
        content = SYSUSERS.read_text()
        self.assertIn("g     sovereign-pihole-secrets -", content)
        # Not "sovereign-conversation" (exactly) -- that would collide with
        # sovereign-conversation.service's own DynamicUser-derived identity,
        # the same real failure mode found on hardware for
        # sovereign-console-secrets.
        self.assertNotIn("g     sovereign-conversation -", content)


if __name__ == "__main__":
    unittest.main()
