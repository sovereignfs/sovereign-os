import http.client
import json
import runpy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
APPLIANCE = ROOT / "image-builder/sovereign/appliance"
AUTH_SERVICE = APPLIANCE / "bin/console-auth"
PASSWORD_SCRIPT = OVERLAY / "usr/sbin/sovereign-console-password"
SYSTEMD_SERVICE = OVERLAY / "etc/systemd/system/sovereign-console-auth.service"
SYSUSERS = OVERLAY / "usr/lib/sysusers.d/sovereign-console.conf"
PROOF_INIT = OVERLAY / "usr/lib/sovereign/proof-init"
PROOF_SERVICE = OVERLAY / "etc/systemd/system/sovereign-proof.service"
NGINX = APPLIANCE / "nginx/sovereign.conf"
ENABLE_UNITS = (
    ROOT
    / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
)


class HashingTests(unittest.TestCase):
    def setUp(self):
        self.module = runpy.run_path(str(AUTH_SERVICE))

    def test_round_trips_and_rejects_wrong_password(self):
        encoded = self.module["hash_password"]("correct horse battery staple")
        self.assertTrue(self.module["verify_password"]("correct horse battery staple", encoded))
        self.assertFalse(self.module["verify_password"]("wrong password entirely", encoded))

    def test_rejects_malformed_hash(self):
        self.assertFalse(self.module["verify_password"]("anything", "not-a-real-hash"))
        self.assertFalse(self.module["verify_password"]("anything", "pbkdf2_sha256$bad$$"))

    def test_rejects_unknown_algorithm(self):
        encoded = "md5$1000$c2FsdA==$aGFzaA=="
        self.assertFalse(self.module["verify_password"]("anything", encoded))


class LiveAuthServer:
    def __init__(self, credential_path, session_seconds=8 * 60 * 60):
        self.credential_path = credential_path
        with mock.patch.dict(
            __import__("os").environ,
            {
                "SOVEREIGN_CONSOLE_CREDENTIAL_PATH": str(credential_path),
                "SOVEREIGN_CONSOLE_SESSION_SECONDS": str(session_seconds),
            },
        ):
            self.module = runpy.run_path(str(AUTH_SERVICE))
        from http.server import ThreadingHTTPServer

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.module["AuthHandler"])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server.server_port

    def connection(self):
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def set_password(self, password):
        encoded = self.module["hash_password"](password)
        self.credential_path.write_text(encoded + "\n")

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


class AuthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.credential_path = Path(self.temporary.name) / "admin-password.hash"
        self.live = LiveAuthServer(self.credential_path)
        self.addCleanup(self.live.stop)

    def _login(self, password, source_ip="203.0.113.10"):
        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/auth/login",
            body=json.dumps({"password": password}),
            headers={"Content-Type": "application/json", "X-Real-IP": source_ip},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response, body

    def test_login_before_credential_is_set_reports_not_configured(self):
        response, body = self._login("whatever it might be")
        self.assertEqual(503, response.status)
        self.assertEqual("not_configured", body["error"])

    def test_wrong_password_is_rejected_without_a_session(self):
        self.live.set_password("correct horse battery staple")
        response, body = self._login("definitely the wrong password")
        self.assertEqual(401, response.status)
        self.assertFalse(body["authenticated"])
        self.assertIsNone(response.getheader("Set-Cookie"))

    def test_correct_password_issues_session_cookie_and_csrf_token(self):
        self.live.set_password("correct horse battery staple")
        response, body = self._login("correct horse battery staple")
        self.assertEqual(200, response.status)
        self.assertTrue(body["authenticated"])
        self.assertIn("csrf_token", body)
        cookie = response.getheader("Set-Cookie")
        self.assertIn("sovereign_console_session=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertNotIn("Secure", cookie)

    def test_session_endpoint_reflects_cookie_state(self):
        self.live.set_password("correct horse battery staple")
        login_response, login_body = self._login("correct horse battery staple")

        connection = self.live.connection()
        connection.request("GET", "/api/v1/auth/session")
        anonymous_response = connection.getresponse()
        anonymous_body = json.loads(anonymous_response.read())
        connection.close()
        self.assertFalse(anonymous_body["authenticated"])

        self.assertIn("csrf_token", login_body)

    def test_session_endpoint_returns_csrf_token_for_a_reloaded_page(self):
        self.live.set_password("correct horse battery staple")
        login_response, login_body = self._login("correct horse battery staple")
        cookie = login_response.getheader("Set-Cookie").split(";")[0]

        connection = self.live.connection()
        connection.request("GET", "/api/v1/auth/session", headers={"Cookie": cookie})
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()

        self.assertTrue(body["authenticated"])
        self.assertEqual(login_body["csrf_token"], body["csrf_token"])

    def test_logout_requires_matching_csrf_token(self):
        self.live.set_password("correct horse battery staple")
        login_response, login_body = self._login("correct horse battery staple")
        cookie = login_response.getheader("Set-Cookie").split(";")[0]

        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/auth/logout",
            headers={"Cookie": cookie, "X-CSRF-Token": "not the real token"},
        )
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(403, response.status)

        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/auth/logout",
            headers={"Cookie": cookie, "X-CSRF-Token": login_body["csrf_token"]},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        self.assertEqual(200, response.status)
        self.assertFalse(body["authenticated"])

    def test_repeated_failures_from_one_source_are_rate_limited(self):
        self.live.set_password("correct horse battery staple")
        source_ip = "203.0.113.55"
        for _ in range(5):
            response, _ = self._login("wrong password", source_ip=source_ip)
            self.assertEqual(401, response.status)

        response, body = self._login("wrong password", source_ip=source_ip)
        self.assertEqual(429, response.status)
        self.assertEqual("rate_limited", body["error"])
        self.assertIsNotNone(response.getheader("Retry-After"))

        other_source_response, _ = self._login("wrong password", source_ip="203.0.113.99")
        self.assertEqual(401, other_source_response.status)

    def test_invalid_request_body_is_rejected(self):
        self.live.set_password("correct horse battery staple")
        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/auth/login",
            body="not json",
            headers={"Content-Type": "application/json", "X-Real-IP": "203.0.113.20"},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        self.assertEqual(400, response.status)
        self.assertEqual("invalid_request", body["error"])


class SessionExpiryTests(unittest.TestCase):
    def test_session_expires_after_its_lifetime(self):
        module = runpy.run_path(str(AUTH_SERVICE))
        with mock.patch.dict(
            module["create_session"].__globals__, {"SESSION_LIFETIME_SECONDS": 0}
        ):
            token, _csrf, _expires = module["create_session"]()
        time.sleep(0.01)
        self.assertIsNone(module["lookup_session"](token))


class ConsoleAuthProvisioningTests(unittest.TestCase):
    def test_group_declared_via_sysusers(self):
        self.assertIn("g", SYSUSERS.read_text())
        self.assertIn("sovereign-console", SYSUSERS.read_text())

    def test_systemd_unit_is_hardened_and_grouped(self):
        service = SYSTEMD_SERVICE.read_text()
        self.assertIn("DynamicUser=yes", service)
        self.assertIn("SupplementaryGroups=sovereign-console", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("CapabilityBoundingSet=", service)
        self.assertIn(
            "ExecStart=/opt/sovereign/current/appliance/bin/console-auth",
            service,
        )
        self.assertIn("After=", service)
        self.assertIn("systemd-sysusers.service", service)

    def test_proof_init_creates_group_scoped_directory_and_validates_binary(self):
        content = PROOF_INIT.read_text()
        self.assertIn(
            "install -d -m 0750 -o root -g sovereign-console /data/sovereign/console",
            content,
        )
        self.assertIn('test -x "$release_dir/appliance/bin/console-auth"', content)

    def test_proof_service_orders_after_sysusers(self):
        self.assertIn("systemd-sysusers.service", PROOF_SERVICE.read_text())

    def test_nginx_proxies_auth_routes_with_real_ip(self):
        nginx = NGINX.read_text()
        for path in ("login", "logout", "session"):
            block_start = nginx.index(f"location = /api/v1/auth/{path} {{")
            block_end = nginx.index("}", block_start)
            block = nginx[block_start:block_end]
            self.assertIn(f"127.0.0.1:8091/api/v1/auth/{path}", block)
            self.assertIn("proxy_set_header X-Real-IP $remote_addr;", block)

    def test_auth_service_is_enabled(self):
        self.assertIn("sovereign-console-auth.service", ENABLE_UNITS.read_text())

    def test_password_script_requires_root_and_terminal(self):
        content = PASSWORD_SCRIPT.read_text()
        self.assertIn("geteuid", content)
        self.assertIn("isatty", content)
        self.assertIn("MINIMUM_LENGTH = 12", content)
        self.assertIn("pbkdf2_hmac", content)
        self.assertIn("0o640", content)
        self.assertIn("0o750", content)


if __name__ == "__main__":
    unittest.main()
