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
SYSUSERS = OVERLAY / "usr/lib/sysusers.d/sovereign-console-secrets.conf"
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
    def __init__(
        self,
        credential_path,
        session_seconds=8 * 60 * 60,
        trigger_path=None,
        install_trigger_path=None,
        update_check_path=None,
    ):
        self.credential_path = credential_path
        environment = {
            "SOVEREIGN_CONSOLE_CREDENTIAL_PATH": str(credential_path),
            "SOVEREIGN_CONSOLE_SESSION_SECONDS": str(session_seconds),
        }
        if trigger_path is not None:
            environment["SOVEREIGN_CONSOLE_CHECK_TRIGGER_PATH"] = str(trigger_path)
        if install_trigger_path is not None:
            environment["SOVEREIGN_CONSOLE_INSTALL_TRIGGER_PATH"] = str(install_trigger_path)
        if update_check_path is not None:
            environment["SOVEREIGN_CONSOLE_UPDATE_CHECK_PATH"] = str(update_check_path)
        with mock.patch.dict(__import__("os").environ, environment):
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

    def test_verify_endpoint_reflects_session_state_with_no_body(self):
        connection = self.live.connection()
        connection.request("GET", "/api/v1/auth/verify")
        anonymous_response = connection.getresponse()
        anonymous_body = anonymous_response.read()
        connection.close()
        self.assertEqual(401, anonymous_response.status)
        self.assertEqual(b"", anonymous_body)

        self.live.set_password("correct horse battery staple")
        login_response, _ = self._login("correct horse battery staple")
        cookie = login_response.getheader("Set-Cookie").split(";")[0]

        connection = self.live.connection()
        connection.request("GET", "/api/v1/auth/verify", headers={"Cookie": cookie})
        response = connection.getresponse()
        body = response.read()
        connection.close()
        self.assertEqual(204, response.status)
        self.assertEqual(b"", body)

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


class CheckTriggerEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        self.credential_path = directory / "admin-password.hash"
        self.trigger_path = directory / "actions/check.request"
        self.live = LiveAuthServer(self.credential_path, trigger_path=self.trigger_path)
        self.addCleanup(self.live.stop)
        self.live.set_password("correct horse battery staple")

    def _authenticated_session(self):
        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/auth/login",
            body=json.dumps({"password": "correct horse battery staple"}),
            headers={"Content-Type": "application/json", "X-Real-IP": "203.0.113.10"},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        cookie = response.getheader("Set-Cookie").split(";")[0]
        return cookie, body["csrf_token"]

    def test_trigger_requires_authentication(self):
        connection = self.live.connection()
        connection.request("POST", "/api/v1/console/actions/check")
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        self.assertEqual(401, response.status)
        self.assertEqual("not_authenticated", body["error"])
        self.assertFalse(self.trigger_path.exists())

    def test_trigger_requires_matching_csrf_token(self):
        cookie, _csrf = self._authenticated_session()
        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/console/actions/check",
            headers={"Cookie": cookie, "X-CSRF-Token": "wrong token"},
        )
        response = connection.getresponse()
        response.read()
        connection.close()
        self.assertEqual(403, response.status)
        self.assertFalse(self.trigger_path.exists())

    def test_authenticated_trigger_writes_the_request_file(self):
        cookie, csrf = self._authenticated_session()
        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/console/actions/check",
            headers={"Cookie": cookie, "X-CSRF-Token": csrf},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        self.assertEqual(202, response.status)
        self.assertTrue(body["triggered"])
        self.assertTrue(self.trigger_path.is_file())

    def test_repeated_triggers_are_cooled_down(self):
        cookie, csrf = self._authenticated_session()

        def trigger():
            connection = self.live.connection()
            connection.request(
                "POST",
                "/api/v1/console/actions/check",
                headers={"Cookie": cookie, "X-CSRF-Token": csrf},
            )
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
            return response, body

        first_response, _first_body = trigger()
        self.assertEqual(202, first_response.status)

        second_response, second_body = trigger()
        self.assertEqual(429, second_response.status)
        self.assertEqual("cooldown", second_body["error"])
        self.assertIsNotNone(second_response.getheader("Retry-After"))


class InstallTriggerEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        directory = Path(self.temporary.name)
        self.credential_path = directory / "admin-password.hash"
        self.trigger_path = directory / "actions/install.request"
        self.update_check_path = directory / "update-check.json"
        self.live = LiveAuthServer(
            self.credential_path,
            install_trigger_path=self.trigger_path,
            update_check_path=self.update_check_path,
        )
        self.addCleanup(self.live.stop)
        self.live.set_password("correct horse battery staple")

    def _set_update_available(self, available):
        self.update_check_path.parent.mkdir(parents=True, exist_ok=True)
        self.update_check_path.write_text(
            json.dumps({"status": "update_available" if available else "up_to_date"})
        )

    def _authenticated_session(self):
        connection = self.live.connection()
        connection.request(
            "POST",
            "/api/v1/auth/login",
            body=json.dumps({"password": "correct horse battery staple"}),
            headers={"Content-Type": "application/json", "X-Real-IP": "203.0.113.10"},
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        cookie = response.getheader("Set-Cookie").split(";")[0]
        return cookie, body["csrf_token"]

    def _trigger(self, cookie, csrf, password=None, source_ip="203.0.113.10"):
        connection = self.live.connection()
        headers = {
            "Cookie": cookie,
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
            "X-Real-IP": source_ip,
        }
        connection.request(
            "POST",
            "/api/v1/console/actions/install",
            body=json.dumps({"password": password}) if password is not None else "",
            headers=headers,
        )
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response, body

    def test_trigger_requires_authentication(self):
        connection = self.live.connection()
        connection.request("POST", "/api/v1/console/actions/install")
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        self.assertEqual(401, response.status)
        self.assertEqual("not_authenticated", body["error"])
        self.assertFalse(self.trigger_path.exists())

    def test_trigger_requires_matching_csrf_token(self):
        cookie, _csrf = self._authenticated_session()
        response, _body = self._trigger(cookie, "wrong token", password="correct horse battery staple")
        self.assertEqual(403, response.status)
        self.assertFalse(self.trigger_path.exists())

    def test_valid_session_alone_is_not_enough_without_the_password(self):
        self._set_update_available(True)
        cookie, csrf = self._authenticated_session()
        response, body = self._trigger(cookie, csrf, password="the wrong password")
        self.assertEqual(401, response.status)
        self.assertEqual("invalid_credentials", body["error"])
        self.assertFalse(self.trigger_path.exists())

    def test_refuses_to_trigger_when_no_update_was_discovered(self):
        self._set_update_available(False)
        cookie, csrf = self._authenticated_session()
        response, body = self._trigger(cookie, csrf, password="correct horse battery staple")
        self.assertEqual(409, response.status)
        self.assertEqual("no_update_available", body["error"])
        self.assertFalse(self.trigger_path.exists())

    def test_correct_password_and_available_update_writes_the_trigger_file(self):
        self._set_update_available(True)
        cookie, csrf = self._authenticated_session()
        response, body = self._trigger(cookie, csrf, password="correct horse battery staple")
        self.assertEqual(202, response.status)
        self.assertTrue(body["triggered"])
        self.assertTrue(self.trigger_path.is_file())

    def test_repeated_triggers_are_cooled_down(self):
        self._set_update_available(True)
        cookie, csrf = self._authenticated_session()

        first_response, _first_body = self._trigger(
            cookie, csrf, password="correct horse battery staple"
        )
        self.assertEqual(202, first_response.status)

        second_response, second_body = self._trigger(
            cookie, csrf, password="correct horse battery staple"
        )
        self.assertEqual(429, second_response.status)
        self.assertEqual("cooldown", second_body["error"])
        self.assertIsNotNone(second_response.getheader("Retry-After"))


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
        content = SYSUSERS.read_text()
        self.assertIn("g     sovereign-console-secrets -", content)
        # Not "sovereign-console" (exactly) -- that collides with
        # sovereign-console.service's own DynamicUser-derived identity.
        # Found on real hardware: console-health refused to restart at
        # all once a static group of that exact name existed.
        self.assertNotIn("g     sovereign-console -", content)

    def test_systemd_unit_is_hardened_and_grouped(self):
        service = SYSTEMD_SERVICE.read_text()
        self.assertIn("DynamicUser=yes", service)
        self.assertIn("SupplementaryGroups=sovereign-console-secrets", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("CapabilityBoundingSet=", service)
        self.assertIn(
            "ExecStart=/opt/sovereign/current/appliance/bin/console-auth",
            service,
        )
        self.assertIn("After=", service)
        self.assertIn("systemd-sysusers.service", service)
        # ProtectSystem=strict makes the whole filesystem read-only except
        # explicitly declared paths -- found missing on real hardware when
        # the check-trigger endpoint's write silently failed (503
        # trigger_unavailable) despite passing every unit test, since no
        # test exercised the real sandboxed filesystem.
        self.assertIn("ReadWritePaths=/data/sovereign/console/actions", service)

    def test_proof_init_creates_group_scoped_directory_and_validates_binary(self):
        content = PROOF_INIT.read_text()
        self.assertIn(
            "install -d -m 0750 -o root -g sovereign-console-secrets"
            " /data/sovereign/console",
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


class CheckTriggerProvisioningTests(unittest.TestCase):
    PATH_UNIT = OVERLAY / "etc/systemd/system/sovereign-console-check-trigger.path"
    SERVICE_UNIT = OVERLAY / "etc/systemd/system/sovereign-console-check-trigger.service"

    def test_path_unit_watches_the_trigger_file_and_activates_the_service(self):
        content = self.PATH_UNIT.read_text()
        self.assertIn(
            "PathExists=/data/sovereign/console/actions/check.request", content
        )
        self.assertIn("Unit=sovereign-console-check-trigger.service", content)

    def test_service_unit_removes_the_trigger_before_running_check_as_root(self):
        content = self.SERVICE_UNIT.read_text()
        self.assertIn(
            "ExecStartPre=/usr/bin/rm -f /data/sovereign/console/actions/check.request",
            content,
        )
        self.assertIn("ExecStart=/usr/sbin/sovereign-update check", content)
        self.assertIn("NoNewPrivileges=yes", content)
        self.assertIn("ReadWritePaths=/data/sovereign", content)

    def test_proof_init_creates_group_writable_actions_directory(self):
        content = PROOF_INIT.read_text()
        self.assertIn(
            "install -d -m 0730 -o root -g sovereign-console-secrets"
            " /data/sovereign/console/actions",
            content,
        )

    def test_check_trigger_path_unit_is_enabled(self):
        self.assertIn(
            "sovereign-console-check-trigger.path", ENABLE_UNITS.read_text()
        )

    def test_nginx_proxies_new_routes(self):
        nginx = NGINX.read_text()
        trigger_start = nginx.index("location = /api/v1/console/actions/check {")
        trigger_block = nginx[trigger_start : nginx.index("}", trigger_start)]
        self.assertIn("127.0.0.1:8091/api/v1/console/actions/check", trigger_block)
        self.assertIn("proxy_set_header X-Real-IP $remote_addr;", trigger_block)

        read_start = nginx.index("location = /api/v1/update/check {")
        read_block = nginx[read_start : nginx.index("}", read_start)]
        self.assertIn("127.0.0.1:8090/api/v1/update/check", read_block)


class InstallTriggerProvisioningTests(unittest.TestCase):
    PATH_UNIT = OVERLAY / "etc/systemd/system/sovereign-console-install-trigger.path"
    SERVICE_UNIT = OVERLAY / "etc/systemd/system/sovereign-console-install-trigger.service"

    def test_path_unit_watches_the_trigger_file_and_activates_the_service(self):
        content = self.PATH_UNIT.read_text()
        self.assertIn(
            "PathExists=/data/sovereign/console/actions/install.request", content
        )
        self.assertIn("Unit=sovereign-console-install-trigger.service", content)

    def test_service_unit_removes_the_trigger_before_running_install_as_root(self):
        content = self.SERVICE_UNIT.read_text()
        self.assertIn(
            "ExecStartPre=/usr/bin/rm -f /data/sovereign/console/actions/install.request",
            content,
        )
        self.assertIn("ExecStart=/usr/sbin/sovereign-update install", content)
        self.assertIn("NoNewPrivileges=yes", content)
        self.assertIn("ReadWritePaths=/data/sovereign", content)
        # A real install can take minutes (bundle download + prepare/backup/
        # stage/activate) -- systemd's default 90s TimeoutStartSec would
        # kill it mid-transaction, a worse failure mode than a slow
        # install completing normally.
        self.assertIn("TimeoutStartSec=0", content)

    def test_service_unit_grants_capabilities_nginx_config_test_needs(self):
        # nginx -t is not a pure parse: it actually binds every listen
        # socket (needs CAP_NET_BIND_SERVICE for 0.0.0.0:80) and chowns
        # worker-owned temp directories to the configured user (needs
        # CAP_CHOWN). verify-update-health shells out to `nginx -t` as
        # part of sovereign-update install's health gates, so this unit
        # needs both even though it never itself binds a port or chowns a
        # file directly. Confirmed on real hardware, one at a time, each
        # as a distinct PREUPDATE_HEALTH_FAILED with a different errno
        # (ADR-0009 qualification, attempts 5 and 7).
        content = self.SERVICE_UNIT.read_text()
        self.assertIn("CapabilityBoundingSet=", content)
        bounding_set_line = next(
            line for line in content.splitlines() if line.startswith("CapabilityBoundingSet=")
        )
        self.assertIn("CAP_NET_BIND_SERVICE", bounding_set_line)
        self.assertIn("CAP_CHOWN", bounding_set_line)

    def test_install_trigger_path_unit_is_enabled(self):
        self.assertIn(
            "sovereign-console-install-trigger.path", ENABLE_UNITS.read_text()
        )

    def test_nginx_proxies_new_routes(self):
        nginx = NGINX.read_text()
        trigger_start = nginx.index("location = /api/v1/console/actions/install {")
        trigger_block = nginx[trigger_start : nginx.index("}", trigger_start)]
        self.assertIn("127.0.0.1:8091/api/v1/console/actions/install", trigger_block)
        self.assertIn("proxy_set_header X-Real-IP $remote_addr;", trigger_block)

        read_start = nginx.index("location = /api/v1/update/status {")
        read_block = nginx[read_start : nginx.index("}", read_start)]
        self.assertIn("127.0.0.1:8090/api/v1/update/status", read_block)


class ServiceGatingProvisioningTests(unittest.TestCase):
    """ADR-0010: /dns/ gated behind Console's session via auth_request."""

    LAYER = ROOT / "image-builder/sovereign/layer/sovereign-proof.yaml"

    def test_nginx_package_is_unchanged(self):
        # Confirmed on real hardware qualification (2026-08-06): this
        # image's Debian 13 (trixie) base no longer splits nginx into
        # nginx-light/-full/-extras -- "nginx-full" isn't even an
        # installable package on trixie -- and the single unified "nginx"
        # package already ships --with-http_auth_request_module. No package
        # change is needed for ADR-0010's auth_request gate.
        packages = self.LAYER.read_text()
        self.assertIn("- nginx\n", packages)
        self.assertNotIn("nginx-full", packages)

    def test_verify_internal_location_is_internal_only(self):
        nginx = NGINX.read_text()
        start = nginx.index("location = /api/v1/auth/verify-internal {")
        block = nginx[start : nginx.index("}", start)]
        self.assertIn("internal;", block)
        self.assertIn("127.0.0.1:8091/api/v1/auth/verify", block)
        self.assertIn("proxy_pass_request_body off;", block)

    def test_dns_location_is_gated_behind_the_verify_subrequest(self):
        nginx = NGINX.read_text()
        start = nginx.index("location /dns/ {")
        block = nginx[start : nginx.index("\n    }", start)]
        self.assertIn("auth_request /api/v1/auth/verify-internal;", block)
        self.assertIn("error_page 401 = @signin;", block)
        self.assertIn("127.0.0.1:8080/", block)

    def test_signin_redirect_preserves_the_original_path(self):
        nginx = NGINX.read_text()
        start = nginx.index("location @signin {")
        block = nginx[start : nginx.index("}", start)]
        self.assertIn("return 302 /console/?next=$request_uri;", block)


if __name__ == "__main__":
    unittest.main()
