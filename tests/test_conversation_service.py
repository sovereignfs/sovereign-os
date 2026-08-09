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
import sovereign_system as system  # noqa: E402


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
    # rules: list of (url_substring, response) consumed in order, one per
    # matching call -- mirrors that a single turn can call the same path
    # (e.g. /v1/chat/completions) more than once across propose/execute
    # rounds, each needing its own canned response.
    remaining = list(rules)

    def _urlopen(request, timeout=None):
        url = request.full_url
        for index, (substring, response) in enumerate(remaining):
            if substring in url:
                del remaining[index]
                return response
        raise AssertionError(f"unexpected urlopen call: {url} (remaining rules: {remaining})")

    return _urlopen


class LiveConversationServer:
    def __init__(self, audit_log_path):
        environment = {"SOVEREIGN_CONVERSATION_AUDIT_LOG_PATH": str(audit_log_path)}
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

    def _post_message(self, payload):
        connection = self.live.connection()
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload)
        else:
            body = payload
        connection.request(
            "POST",
            "/api/v1/conversation/message",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        parsed = json.loads(response.read())
        connection.close()
        return response, parsed

    def test_health_endpoint_reports_provider_health(self):
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
                [("/v1/chat/completions", chat_completion(content="Hello there."))]
            )
            response, body = self._post_message({"message": "hi"})
        self.assertEqual(200, response.status)
        self.assertEqual("Hello there.", body["text"])
        self.assertEqual([], body["capability_events"])

    def test_missing_message_is_rejected(self):
        response, body = self._post_message({})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_non_list_messages_history_is_rejected(self):
        response, body = self._post_message({"message": "hi", "messages": "not a list"})
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_malformed_json_body_is_rejected(self):
        response, body = self._post_message("not json")
        self.assertEqual(400, response.status)
        self.assertEqual("INVALID_REQUEST", body["error"]["code"])

    def test_capability_proposal_executes_against_the_real_registry_and_narrates(self):
        proposal = chat_completion(tool_calls=[tool_call("call_1_0", "system.health", {})])
        narration = chat_completion(content="The system is healthy.")
        with mock.patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = dispatch_urlopen(
                [
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
            urlopen.side_effect = urllib.error.URLError("connection refused")
            response, body = self._post_message({"message": "hi"})
        self.assertEqual(502, response.status)
        self.assertEqual("PROVIDER_UNAVAILABLE", body["error"]["code"])


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
