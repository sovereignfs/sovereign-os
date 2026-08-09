import io
import json
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_pihole as pihole  # noqa: E402


def json_response(payload, status=200):
    body = json.dumps(payload).encode("utf-8")
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = body
    response.status = status
    return response


def http_error(status, error_key):
    body = json.dumps({"error": {"key": error_key, "message": error_key, "hint": None}, "took": 0.001}).encode("utf-8")
    return urllib.error.HTTPError(url="http://127.0.0.1:8080/api/x", code=status, msg=error_key, hdrs=None, fp=io.BytesIO(body))


class PiholeTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.password_path = Path(self.tempdir.name) / "pihole-admin-password"
        self.password_path.write_text("correct horse battery staple\n")
        self.audit_path = Path(self.tempdir.name) / "audit.jsonl"

    def session(self):
        return pihole.PiholeSession(password_path=self.password_path)

    def authenticated_session(self):
        session = self.session()
        session._sid = "abc"
        session._expires_at = time.monotonic() + 1800
        return session


class AuthenticationTests(PiholeTestCase):
    @mock.patch("urllib.request.urlopen")
    def test_successful_auth_returns_sid(self, urlopen):
        urlopen.return_value = json_response(
            {"session": {"valid": True, "sid": "abc", "validity": 1800, "message": "password correct"}, "took": 0.1}
        )
        session = self.session()
        self.assertEqual(session.sid(), "abc")

    @mock.patch("urllib.request.urlopen")
    def test_sid_is_reused_within_validity(self, urlopen):
        urlopen.return_value = json_response(
            {"session": {"valid": True, "sid": "abc", "validity": 1800, "message": "password correct"}, "took": 0.1}
        )
        session = self.session()
        session.sid()
        session.sid()
        self.assertEqual(urlopen.call_count, 1)

    @mock.patch("urllib.request.urlopen")
    def test_session_reauthenticates_after_expiry(self, urlopen):
        urlopen.return_value = json_response(
            {"session": {"valid": True, "sid": "abc", "validity": 0, "message": "password correct"}, "took": 0.1}
        )
        session = self.session()
        session.sid()
        session.sid()
        self.assertGreaterEqual(urlopen.call_count, 2)

    @mock.patch("urllib.request.urlopen")
    def test_wrong_password_raises_auth_failed(self, urlopen):
        urlopen.return_value = json_response(
            {"session": {"valid": False, "sid": None, "validity": -1, "message": "password incorrect"}, "took": 0.1}
        )
        session = self.session()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            session.sid()
        self.assertEqual(caught.exception.code, "PIHOLE_AUTH_FAILED")

    def test_missing_credential_file_raises(self):
        session = pihole.PiholeSession(password_path=Path(self.tempdir.name) / "does-not-exist")
        with self.assertRaises(capabilities.CapabilityError) as caught:
            session.sid()
        self.assertEqual(caught.exception.code, "PIHOLE_CREDENTIAL_UNAVAILABLE")

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_during_auth_raises(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        session = self.session()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            session.sid()
        self.assertEqual(caught.exception.code, "PIHOLE_UNREACHABLE")


class PiholeGetTests(PiholeTestCase):
    @mock.patch("urllib.request.urlopen")
    def test_requests_are_always_get(self, urlopen):
        urlopen.return_value = json_response({"blocking": "enabled", "timer": None, "took": 0.1})
        pihole.pihole_get(self.authenticated_session(), "/dns/blocking")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.get_method(), "GET")

    @mock.patch("urllib.request.urlopen")
    def test_401_triggers_one_reauth_and_retry(self, urlopen):
        reauth_response = json_response(
            {"session": {"valid": True, "sid": "new-sid", "validity": 1800, "message": "password correct"}, "took": 0.1}
        )
        success_response = json_response({"blocking": "enabled", "timer": None, "took": 0.1})
        urlopen.side_effect = [http_error(401, "unauthorized"), reauth_response, success_response]
        result = pihole.pihole_get(self.authenticated_session(), "/dns/blocking")
        self.assertEqual(result["blocking"], "enabled")
        self.assertEqual(urlopen.call_count, 3)

    @mock.patch("urllib.request.urlopen")
    def test_persistent_401_does_not_loop_forever(self, urlopen):
        reauth_response = json_response(
            {"session": {"valid": True, "sid": "new-sid", "validity": 1800, "message": "password correct"}, "took": 0.1}
        )
        urlopen.side_effect = [http_error(401, "unauthorized"), reauth_response, http_error(401, "unauthorized")]
        with self.assertRaises(capabilities.CapabilityError) as caught:
            pihole.pihole_get(self.authenticated_session(), "/dns/blocking")
        self.assertEqual(caught.exception.code, "PIHOLE_UNAUTHORIZED")
        self.assertEqual(urlopen.call_count, 3)

    @mock.patch("urllib.request.urlopen")
    def test_rate_limiting_maps_to_typed_error(self, urlopen):
        urlopen.side_effect = http_error(429, "rate_limiting")
        with self.assertRaises(capabilities.CapabilityError) as caught:
            pihole.pihole_get(self.authenticated_session(), "/dns/blocking")
        self.assertEqual(caught.exception.code, "PIHOLE_RATE_LIMITED")

    @mock.patch("urllib.request.urlopen")
    def test_seat_exhaustion_maps_to_typed_error(self, urlopen):
        urlopen.side_effect = http_error(429, "api_seats_exceeded")
        with self.assertRaises(capabilities.CapabilityError) as caught:
            pihole.pihole_get(self.authenticated_session(), "/dns/blocking")
        self.assertEqual(caught.exception.code, "PIHOLE_SESSION_LIMIT_EXCEEDED")

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_maps_to_typed_error(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(capabilities.CapabilityError) as caught:
            pihole.pihole_get(self.authenticated_session(), "/dns/blocking")
        self.assertEqual(caught.exception.code, "PIHOLE_UNREACHABLE")


class StatusImplementationTests(PiholeTestCase):
    @mock.patch("urllib.request.urlopen")
    def test_enabled_maps_true(self, urlopen):
        urlopen.return_value = json_response({"blocking": "enabled", "timer": None, "took": 0.1})
        result = pihole.make_status_implementation(self.authenticated_session())({})
        self.assertEqual(result, {"reachable": True, "blocking_enabled": True, "checked_at": result["checked_at"]})

    @mock.patch("urllib.request.urlopen")
    def test_disabled_maps_false(self, urlopen):
        urlopen.return_value = json_response({"blocking": "disabled", "timer": None, "took": 0.1})
        result = pihole.make_status_implementation(self.authenticated_session())({})
        self.assertEqual(result["blocking_enabled"], False)

    @mock.patch("urllib.request.urlopen")
    def test_failed_and_unknown_map_to_null_never_guessed(self, urlopen):
        for raw in ("failed", "unknown"):
            urlopen.return_value = json_response({"blocking": raw, "timer": None, "took": 0.1})
            result = pihole.make_status_implementation(self.authenticated_session())({})
            self.assertIsNone(result["blocking_enabled"])

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_pihole_is_a_valid_result_not_an_error(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        result = pihole.make_status_implementation(self.authenticated_session())({})
        self.assertEqual(result["reachable"], False)
        self.assertIsNone(result["blocking_enabled"])

    @mock.patch("urllib.request.urlopen")
    def test_genuine_auth_failure_is_not_masked_as_unreachable(self, urlopen):
        # Deliberately unauthenticated (not authenticated_session()): this
        # must actually exercise the auth round trip to test that a real
        # "password incorrect" response is reported as PIHOLE_AUTH_FAILED,
        # not silently folded into the unreachable/degraded-status path.
        urlopen.return_value = json_response(
            {"session": {"valid": False, "sid": None, "validity": -1, "message": "password incorrect"}, "took": 0.1}
        )
        with self.assertRaises(capabilities.CapabilityError) as caught:
            pihole.make_status_implementation(self.session())({})
        self.assertEqual(caught.exception.code, "PIHOLE_AUTH_FAILED")


class SummaryImplementationTests(PiholeTestCase):
    @mock.patch("urllib.request.urlopen")
    def test_combines_both_endpoints(self, urlopen):
        urlopen.side_effect = [
            json_response({"sum_queries": 460, "sum_blocked": 163, "percent_blocked": 35.4, "total_clients": 6, "took": 0.001}),
            json_response({
                "queries": {"total": 462, "blocked": 165},
                "clients": {"active": 5, "total": 5},
                "gravity": {"domains_being_blocked": 99276, "last_update": 1785830365},
                "took": 0.001,
            }),
        ]
        result = pihole.make_summary_implementation(self.authenticated_session())({"period": "last_24h"})
        self.assertEqual(result["queries_total"], 460)
        self.assertEqual(result["queries_blocked"], 163)
        self.assertEqual(result["blocklist_size"], 99276)
        self.assertEqual(result["unique_clients"], 5)
        self.assertEqual(result["period"], "last_24h")

    @mock.patch("urllib.request.urlopen")
    def test_unreachable_raises_rather_than_fabricating_zero_counts(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(capabilities.CapabilityError) as caught:
            pihole.make_summary_implementation(self.authenticated_session())({"period": "today"})
        self.assertEqual(caught.exception.code, "PIHOLE_UNREACHABLE")


class EndToEndExecutorTests(PiholeTestCase):
    @mock.patch("urllib.request.urlopen")
    def test_status_and_summary_pass_through_the_real_executor(self, urlopen):
        registry = pihole.register(capabilities.Registry(), session=self.authenticated_session())
        urlopen.return_value = json_response({"blocking": "enabled", "timer": None, "took": 0.1})
        result = capabilities.invoke(
            registry, "pihole.status", 1, {}, {}, capabilities.ConfirmationStore(),
            audit_log_path=self.audit_path,
        )
        self.assertEqual(result["blocking_enabled"], True)
        [event] = [json.loads(line) for line in self.audit_path.read_text().splitlines()]
        self.assertEqual(event["outcome"], "executed")
        self.assertEqual(event["side_effect"], "read_only")
        self.assertEqual(event["network"], "local")

    def test_registered_capabilities_are_read_only_local_automatic(self):
        registry = pihole.register(capabilities.Registry(), session=self.authenticated_session())
        status = registry.resolve("pihole.status", 1)
        summary = registry.resolve("pihole.summary", 1)
        for capability in (status, summary):
            self.assertEqual(capability.side_effect, "read_only")
            self.assertEqual(capability.network, "local")
            self.assertEqual(capability.confirmation, "automatic")

    def test_adversarial_extra_field_never_reaches_the_caller(self):
        # Simulates a buggy (or compromised) Pi-hole response leaking a
        # field this capability's declared result_schema doesn't allow --
        # the executor must reject it, not merely trust the implementation.
        registry = capabilities.Registry()
        leaking_status = capabilities.Capability(
            name="pihole.status",
            version=1,
            argument_schema=pihole.STATUS_ARGUMENT_SCHEMA,
            result_schema=pihole.STATUS_RESULT_SCHEMA,
            side_effect="read_only",
            network="local",
            implementation=lambda arguments: {
                "reachable": True, "blocking_enabled": True, "checked_at": "2026-08-09T00:00:00Z",
                "client_ip": "192.168.1.42",
            },
        )
        registry.register(leaking_status)
        with self.assertRaises(capabilities.CapabilityError) as caught:
            capabilities.invoke(
                registry, "pihole.status", 1, {}, {}, capabilities.ConfirmationStore(),
                audit_log_path=self.audit_path,
            )
        self.assertEqual(caught.exception.code, "INVALID_RESULT")


if __name__ == "__main__":
    unittest.main()
