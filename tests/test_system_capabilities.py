import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_system as system  # noqa: E402


def json_response(payload):
    body = json.dumps(payload).encode("utf-8")
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = body
    return response


def healthy_payload(**overrides):
    payload = {
        "schema_version": "1",
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
            "network": [
                {"name": "eth0", "state": "up", "addresses": ["192.168.1.42"]},
            ],
        },
        "checks": {
            "storage": {"status": "healthy", "summary": "Persistent storage available"},
            "dns": {"status": "healthy", "summary": "Resolving normally"},
            "update": {"status": "healthy", "summary": "Latest update committed"},
            "pihole": {"status": "healthy", "summary": "Pi-hole is available"},
            "local_access": {"status": "healthy", "summary": "Console is reachable"},
        },
    }
    payload.update(overrides)
    return payload


class FetchHealthTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_returns_raw_payload(self, urlopen):
        urlopen.return_value = json_response(healthy_payload())
        payload = system.fetch_health()
        self.assertEqual(payload["status"], "healthy")

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_raises_typed_error(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(capabilities.CapabilityError) as caught:
            system.fetch_health()
        self.assertEqual(caught.exception.code, "SYSTEM_HEALTH_UNAVAILABLE")

    @mock.patch("urllib.request.urlopen")
    def test_invalid_json_raises_typed_error(self, urlopen):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = b"not json"
        urlopen.return_value = response
        with self.assertRaises(capabilities.CapabilityError) as caught:
            system.fetch_health()
        self.assertEqual(caught.exception.code, "SYSTEM_HEALTH_INVALID_RESPONSE")


class HealthImplementationTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_maps_healthy_payload(self, urlopen):
        urlopen.return_value = json_response(healthy_payload())
        result = system.make_health_implementation()({})
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["system"]["name"], "Sovereign OS")
        self.assertNotIn("schema_version", result)

    @mock.patch("urllib.request.urlopen")
    def test_drops_console_healths_own_schema_version(self, urlopen):
        urlopen.return_value = json_response(healthy_payload(schema_version="99"))
        result = system.make_health_implementation()({})
        self.assertNotIn("schema_version", result)

    @mock.patch("urllib.request.urlopen")
    def test_null_resource_fields_pass_through(self, urlopen):
        urlopen.return_value = json_response(
            healthy_payload(system={
                **healthy_payload()["system"],
                "memory": None,
                "data_storage": None,
                "temperature_celsius": None,
                "uptime_seconds": None,
            })
        )
        result = system.make_health_implementation()({})
        self.assertIsNone(result["system"]["memory"])
        self.assertIsNone(result["system"]["temperature_celsius"])

    @mock.patch("urllib.request.urlopen")
    def test_degraded_status_passes_through(self, urlopen):
        payload = healthy_payload(status="degraded")
        payload["checks"]["pihole"] = {"status": "degraded", "summary": "Pi-hole is unavailable"}
        urlopen.return_value = json_response(payload)
        result = system.make_health_implementation()({})
        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["checks"]["pihole"]["status"], "degraded")


class EndToEndExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.audit_path = Path(self.tempdir.name) / "audit.jsonl"

    @mock.patch("urllib.request.urlopen")
    def test_passes_through_the_real_executor(self, urlopen):
        urlopen.return_value = json_response(healthy_payload())
        registry = system.register(capabilities.Registry())
        result = capabilities.invoke(
            registry, "system.health", 1, {}, {}, capabilities.ConfirmationStore(),
            audit_log_path=self.audit_path,
        )
        self.assertEqual(result["status"], "healthy")
        [event] = [json.loads(line) for line in self.audit_path.read_text().splitlines()]
        self.assertEqual(event["outcome"], "executed")
        self.assertNotIn("system", event)
        self.assertNotIn("checks", event)

    def test_registered_capability_is_read_only_local_automatic(self):
        registry = system.register(capabilities.Registry())
        capability = registry.resolve("system.health", 1)
        self.assertEqual(capability.side_effect, "read_only")
        self.assertEqual(capability.network, "local")
        self.assertEqual(capability.confirmation, "automatic")

    @mock.patch("urllib.request.urlopen")
    def test_malformed_upstream_response_fails_cleanly_not_uncaught(self, urlopen):
        # A response missing required top-level fields must not crash the
        # executor with a raw, unclassified exception -- RFC-0003's
        # "audit always" guarantee, exercised against a real bug class
        # (an upstream service returning something unexpected).
        urlopen.return_value = json_response({"status": "healthy"})  # missing checked_at/system/checks
        registry = system.register(capabilities.Registry())
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "system.health", 1, {}, {}, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "EXECUTION_FAILED")
        [event] = [json.loads(line) for line in self.audit_path.read_text().splitlines()]
        self.assertEqual(event["outcome"], "rejected")

    @mock.patch("urllib.request.urlopen")
    def test_adversarial_extra_field_never_reaches_the_caller(self, urlopen):
        payload = healthy_payload()
        payload["system"]["serial_number"] = "10000000abcdef01"
        urlopen.return_value = json_response(payload)
        registry = system.register(capabilities.Registry())
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "system.health", 1, {}, {}, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "INVALID_RESULT")


if __name__ == "__main__":
    unittest.main()
