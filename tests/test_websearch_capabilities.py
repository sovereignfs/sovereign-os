import json
import socket
import sys
import tempfile
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / "image-builder/sovereign/appliance/lib"
if str(LIB) not in sys.path:
    sys.path.insert(0, str(LIB))

import sovereign_capabilities as capabilities  # noqa: E402
import sovereign_websearch as websearch  # noqa: E402


def json_response(payload):
    response = mock.MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = json.dumps(payload).encode("utf-8")
    return response


class SearchImplementationTests(unittest.TestCase):
    @mock.patch("urllib.request.urlopen")
    def test_maps_title_url_content_to_title_url_snippet(self, urlopen):
        urlopen.return_value = json_response({
            "query": "raspberry pi",
            "results": [{"title": "Raspberry Pi", "url": "https://www.raspberrypi.com/", "content": "official site", "engine": "duckduckgo"}],
        })
        implementation = websearch.make_search_implementation()
        result = implementation({"query": "raspberry pi"})
        self.assertEqual(
            result["results"],
            [{"title": "Raspberry Pi", "url": "https://www.raspberrypi.com/", "snippet": "official site"}],
        )
        self.assertEqual(result["result_count"], 1)
        self.assertEqual(result["query"], "raspberry pi")

    @mock.patch("urllib.request.urlopen")
    def test_trims_to_the_maximum_result_count(self, urlopen):
        raw = [{"title": f"t{i}", "url": f"u{i}", "content": f"c{i}"} for i in range(20)]
        urlopen.return_value = json_response({"query": "x", "results": raw})
        implementation = websearch.make_search_implementation()
        result = implementation({"query": "x"})
        self.assertEqual(len(result["results"]), websearch.MAX_SEARCH_RESULTS)

    @mock.patch("urllib.request.urlopen")
    def test_missing_optional_fields_default_to_empty_strings_not_a_crash(self, urlopen):
        urlopen.return_value = json_response({"query": "x", "results": [{}]})
        implementation = websearch.make_search_implementation()
        result = implementation({"query": "x"})
        self.assertEqual(result["results"], [{"title": "", "url": "", "snippet": ""}])

    def test_empty_query_is_rejected_before_any_request(self):
        implementation = websearch.make_search_implementation()
        with mock.patch("urllib.request.urlopen") as urlopen:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                implementation({"query": ""})
            urlopen.assert_not_called()
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENTS")

    def test_overlong_query_is_rejected(self):
        implementation = websearch.make_search_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({"query": "x" * (websearch.MAX_QUERY_LENGTH + 1)})
        self.assertEqual(caught.exception.code, "INVALID_ARGUMENTS")

    @mock.patch("urllib.request.urlopen")
    def test_time_range_is_forwarded_when_present(self, urlopen):
        urlopen.return_value = json_response({"query": "x", "results": []})
        implementation = websearch.make_search_implementation()
        implementation({"query": "x", "time_range": "month"})
        requested_url = urlopen.call_args[0][0].full_url
        self.assertIn("time_range=month", requested_url)

    @mock.patch("urllib.request.urlopen")
    def test_no_time_range_argument_omits_it_from_the_request(self, urlopen):
        urlopen.return_value = json_response({"query": "x", "results": []})
        implementation = websearch.make_search_implementation()
        implementation({"query": "x"})
        requested_url = urlopen.call_args[0][0].full_url
        self.assertNotIn("time_range", requested_url)

    @mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused"))
    def test_unreachable_searxng_raises_a_typed_error(self, urlopen):
        implementation = websearch.make_search_implementation()
        with self.assertRaises(capabilities.CapabilityError) as caught:
            implementation({"query": "x"})
        self.assertEqual(caught.exception.code, "SEARXNG_UNREACHABLE")


class UnsafeAddressTests(unittest.TestCase):
    def test_loopback_is_unsafe(self):
        self.assertTrue(websearch._is_unsafe_address("127.0.0.1"))
        self.assertTrue(websearch._is_unsafe_address("::1"))

    def test_rfc1918_private_ranges_are_unsafe(self):
        for ip in ("10.0.0.5", "172.16.0.5", "192.168.1.1"):
            self.assertTrue(websearch._is_unsafe_address(ip), ip)

    def test_link_local_is_unsafe(self):
        self.assertTrue(websearch._is_unsafe_address("169.254.169.254"))

    def test_multicast_is_unsafe(self):
        self.assertTrue(websearch._is_unsafe_address("224.0.0.1"))

    def test_ordinary_public_address_is_safe(self):
        self.assertFalse(websearch._is_unsafe_address("93.184.216.34"))


class ResolveSafeAddressTests(unittest.TestCase):
    def test_rejects_when_any_candidate_is_unsafe(self):
        # A hostname resolving to a mix of public and private addresses is
        # itself untrusted, not just whichever address happens to be
        # connected to first.
        with mock.patch("socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
            ]
            with self.assertRaises(capabilities.CapabilityError) as caught:
                websearch._resolve_safe_address("mixed.example", 443)
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")

    def test_dns_rebinding_style_address_is_rejected(self):
        # Simulates a hostname an attacker controls resolving to an
        # internal address -- the exact scenario a one-time, earlier
        # hostname-string check (rather than checking the address the
        # connection is actually about to use) would miss.
        with mock.patch("socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80)),
            ]
            with self.assertRaises(capabilities.CapabilityError) as caught:
                websearch._resolve_safe_address("looks-external.example", 80)
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")

    def test_unresolvable_host_raises_a_distinct_code(self):
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror("nope")):
            with self.assertRaises(capabilities.CapabilityError) as caught:
                websearch._resolve_safe_address("does-not-exist.invalid", 80)
        self.assertEqual(caught.exception.code, "FETCH_TARGET_UNRESOLVABLE")

    def test_safe_public_address_is_returned(self):
        with mock.patch("socket.getaddrinfo") as getaddrinfo:
            getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            ]
            self.assertEqual(websearch._resolve_safe_address("example.com", 443), "93.184.216.34")


class FetchSSRFTests(unittest.TestCase):
    def test_non_http_scheme_is_rejected_before_resolving_anything(self):
        with mock.patch("socket.getaddrinfo") as getaddrinfo:
            with self.assertRaises(capabilities.CapabilityError) as caught:
                websearch._fetch("file:///etc/passwd")
            getaddrinfo.assert_not_called()
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")

    def test_loopback_target_is_rejected(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            websearch._fetch("http://127.0.0.1:8091/")
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")

    def test_rfc1918_target_is_rejected(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            websearch._fetch("http://10.0.0.5/")
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")

    def test_link_local_metadata_style_target_is_rejected(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            websearch._fetch("http://169.254.169.254/latest/meta-data/")
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")

    def test_ipv6_loopback_target_is_rejected(self):
        with self.assertRaises(capabilities.CapabilityError) as caught:
            websearch._fetch("http://[::1]/")
        self.assertEqual(caught.exception.code, "FETCH_TARGET_REJECTED")


class _FetchTestHandler(BaseHTTPRequestHandler):
    def log_message(self, format_string, *arguments):
        return

    def do_GET(self):
        if self.path == "/html":
            body = b"<html><head><style>.x{color:red}</style></head><body><script>evil()</script><p>Hello <b>world</b></p></body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/large":
            body = b"x" * (websearch.FETCH_MAX_RESPONSE_BYTES + 5000)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/binary":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", "3")
            self.end_headers()
            self.wfile.write(b"\x00\x01\x02")
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "http://internal.example/should-not-be-followed")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()


class FetchHappyPathTests(unittest.TestCase):
    # These exercise the real HTTP machinery (_PinnedHTTPConnection,
    # content-type/size handling, HTML extraction) end to end against a
    # real local server -- only the SSRF address check itself is patched,
    # since a real bound test server is necessarily on a loopback address
    # that the real check would (correctly) refuse.
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _FetchTestHandler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=5)
        cls.server.server_close()

    def fetch(self, path):
        with mock.patch("sovereign_websearch._resolve_safe_address", return_value="127.0.0.1"):
            return websearch._fetch(f"http://looks-external.example:{self.port}{path}")

    def test_html_is_extracted_to_plain_text_excluding_script_and_style(self):
        result = self.fetch("/html")
        self.assertEqual(result["text"], "Hello world")
        self.assertEqual(result["content_type"], "text/html")
        self.assertFalse(result["truncated"])
        self.assertFalse(result["redirected"])

    def test_oversized_response_is_truncated_not_fully_buffered_unbounded(self):
        result = self.fetch("/large")
        self.assertTrue(result["truncated"])
        self.assertLessEqual(len(result["text"].encode("utf-8")), websearch.FETCH_MAX_RESPONSE_BYTES)

    def test_disallowed_content_type_is_rejected(self):
        with mock.patch("sovereign_websearch._resolve_safe_address", return_value="127.0.0.1"):
            with self.assertRaises(capabilities.CapabilityError) as caught:
                websearch._fetch(f"http://looks-external.example:{self.port}/binary")
        self.assertEqual(caught.exception.code, "FETCH_CONTENT_TYPE_REJECTED")

    def test_redirect_is_reported_not_followed(self):
        result = self.fetch("/redirect")
        self.assertTrue(result["redirected"])
        self.assertEqual(result["final_url"], "http://internal.example/should-not-be-followed")
        self.assertEqual(result["text"], "")


class EndToEndExecutorTests(unittest.TestCase):
    def test_registered_capabilities_are_read_only_external_required(self):
        registry = websearch.register(capabilities.Registry())
        for name in ("web.search", "web.fetch"):
            capability = registry.resolve(name, 1)
            self.assertEqual(capability.side_effect, "read_only")
            self.assertEqual(capability.network, "external")
            self.assertEqual(capability.confirmation, "required")

    def test_disabled_by_policy_rejected_before_confirmation(self):
        registry = websearch.register(capabilities.Registry())
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            with self.assertRaises(capabilities.CapabilityError) as caught:
                capabilities.invoke(
                    registry, "web.search", 1, {"query": "x"}, {}, capabilities.ConfirmationStore(),
                    audit_log_path=audit_path,
                )
        self.assertEqual(caught.exception.code, "CAPABILITY_DISABLED")

    @mock.patch("urllib.request.urlopen")
    def test_full_confirmation_round_trip_through_the_real_executor(self, urlopen):
        urlopen.return_value = json_response({"query": "x", "results": []})
        registry = websearch.register(capabilities.Registry())
        store = capabilities.ConfirmationStore()
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            policy = {"external_enabled": True}
            with self.assertRaises(capabilities.CapabilityError) as caught:
                capabilities.invoke(
                    registry, "web.search", 1, {"query": "x"}, policy, store, audit_log_path=audit_path,
                )
            self.assertEqual(caught.exception.code, "CONFIRMATION_REQUIRED")

            token = store.issue("web.search", 1, {"query": "x"})
            result = capabilities.invoke(
                registry, "web.search", 1, {"query": "x"}, policy, store,
                confirmation_token=token, audit_log_path=audit_path,
            )
        self.assertEqual(result["query"], "x")

    def test_adversarial_extra_field_never_reaches_the_caller(self):
        # Simulates a buggy (or compromised) SearXNG response leaking a
        # field this capability's declared result_schema doesn't allow --
        # the executor must reject it, not merely trust the
        # implementation.
        registry = capabilities.Registry()
        leaking_search = capabilities.Capability(
            name="web.search", version=1,
            argument_schema=websearch.SEARCH_ARGUMENT_SCHEMA,
            result_schema=websearch.SEARCH_RESULT_SCHEMA,
            side_effect="read_only", network="external",
            implementation=lambda arguments: {
                "query": "x", "results": [], "result_count": 0,
                "retrieved_at": capabilities.timestamp(),
                "unexpected_field": "leaked",
            },
        )
        registry.register(leaking_search)
        store = capabilities.ConfirmationStore()
        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            token = store.issue("web.search", 1, {"query": "x"})
            with self.assertRaises(capabilities.CapabilityError) as caught:
                capabilities.invoke(
                    registry, "web.search", 1, {"query": "x"}, {"external_enabled": True}, store,
                    confirmation_token=token, audit_log_path=audit_path,
                )
        self.assertEqual(caught.exception.code, "INVALID_RESULT")


if __name__ == "__main__":
    unittest.main()
