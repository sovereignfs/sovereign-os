import json
import os
import runpy
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
HEALTH_SERVICE = OVERLAY / "usr/lib/sovereign/console-health"
SYSTEMD_SERVICE = OVERLAY / "etc/systemd/system/sovereign-console.service"
NGINX = OVERLAY / "etc/nginx/sites-available/sovereign"
HTML = OVERLAY / "usr/share/sovereign-console/index.html"
JAVASCRIPT = OVERLAY / "usr/share/sovereign-console/assets/console.js"
STYLES = OVERLAY / "usr/share/sovereign-console/assets/console.css"
ENABLE_UNITS = (
    ROOT
    / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
)

class ConsoleTests(unittest.TestCase):
    def test_health_server_returns_bounded_healthy_contract(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            state = temporary / "sovereign"
            state.mkdir(parents=True)
            release = temporary / "sovereign-release"
            release.write_text('NAME="Sovereign OS"\nVERSION="test"\n')

            dig = temporary / "dig"
            dig.write_text("#!/bin/sh\nprintf '192.0.2.1\\n'\n")
            dig.chmod(dig.stat().st_mode | stat.S_IXUSR)
            ip = temporary / "ip"
            ip.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' '[{\"ifname\":\"eth0\",\"operstate\":\"UP\","
                "\"addr_info\":[{\"family\":\"inet\",\"local\":\"192.0.2.2\"}]}]'\n"
            )
            ip.chmod(ip.stat().st_mode | stat.S_IXUSR)

            environment = os.environ | {
                "SOVEREIGN_DATA_PATH": str(temporary),
                "SOVEREIGN_RELEASE_PATH": str(release),
                "SOVEREIGN_DIG_PATH": str(dig),
                "SOVEREIGN_IP_PATH": str(ip),
            }
            with mock.patch.dict(os.environ, environment, clear=True):
                module = runpy.run_path(str(HEALTH_SERVICE))
                with mock.patch.dict(
                    module["collect_health"].__globals__,
                    {"tcp_check": lambda port: port in (80, 8080)},
                ):
                    payload = module["collect_health"]()

            self.assertEqual("1", payload["schema_version"])
            self.assertEqual("healthy", payload["status"])
            self.assertEqual("healthy", payload["checks"]["pihole"]["status"])
            self.assertEqual("192.0.2.2", payload["system"]["network"][0]["addresses"][0])
            serialized = json.dumps(payload).lower()
            for forbidden in ("password", "secret", "query_history", "serial"):
                self.assertNotIn(forbidden, serialized)

    def test_health_contract_degrades_when_pihole_is_unavailable(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with mock.patch.dict(
            module["collect_health"].__globals__,
            {
                "marker_check": lambda filename, required: {
                    "status": "healthy",
                    "summary": "Available",
                },
                "dns_check": lambda: {
                    "status": "healthy",
                    "summary": "Resolving normally",
                },
                "tcp_check": lambda port: False,
            },
        ):
            payload = module["collect_health"]()

        self.assertEqual("degraded", payload["status"])
        self.assertEqual("degraded", payload["checks"]["pihole"]["status"])

    def test_update_recovery_is_visible_without_journal_details(self):
        module = runpy.run_path(str(HEALTH_SERVICE))
        with tempfile.TemporaryDirectory() as temporary_directory:
            status = Path(temporary_directory) / "update-status.json"
            status.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "state": "recovery_required",
                        "target_version": "0.1.0-preview.7",
                        "updated_at": "2026-07-22T20:00:00Z",
                    }
                )
            )
            with mock.patch.dict(
                module["update_check"].__globals__,
                {"UPDATE_STATUS_PATH": status},
            ):
                result = module["update_check"]()
        self.assertEqual("degraded", result["status"])
        self.assertNotIn("transaction", json.dumps(result).lower())

    def test_console_routes_and_privilege_boundary(self):
        nginx = NGINX.read_text()
        service = SYSTEMD_SERVICE.read_text()
        enabled = ENABLE_UNITS.read_text()
        nginx_drop_in = (
            OVERLAY
            / "etc/systemd/system/nginx.service.d/10-sovereign-pihole.conf"
        ).read_text()

        self.assertIn("return 302 /console/;", nginx)
        self.assertIn("location = /console/", nginx)
        self.assertIn("location = /console/health/", nginx)
        self.assertIn("location = /api/v1/health", nginx)
        self.assertIn("127.0.0.1:8090/api/v1/health", nginx)
        self.assertIn("try_files /index.html =404;", nginx)
        self.assertNotIn("alias /usr/share/sovereign-console/index.html", nginx)
        self.assertIn("DynamicUser=yes", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectSystem=strict", service)
        self.assertIn("CapabilityBoundingSet=", service)
        self.assertIn("AF_NETLINK", service)
        self.assertNotIn("docker.sock", service)
        self.assertIn("sovereign-console.service", enabled)
        self.assertIn(
            "Wants=sovereign-pihole.service sovereign-console.service",
            nginx_drop_in,
        )
        self.assertNotIn("Requires=sovereign-pihole.service", nginx_drop_in)

    def test_console_assets_are_local_and_safe(self):
        html = HTML.read_text()
        javascript = JAVASCRIPT.read_text()
        styles = STYLES.read_text()
        combined = f"{html}\n{javascript}\n{styles}".lower()

        self.assertIn('href="/console/assets/console.css"', html)
        self.assertIn('src="/console/assets/console.js"', html)
        self.assertIn('href="/dns/admin/"', html)
        self.assertIn('fetch("/api/v1/health"', javascript)
        self.assertNotIn("innerhtml", javascript.lower())
        self.assertNotIn("https://", combined)
        self.assertNotIn("http://", combined)
        for forbidden in ("password", "secret", "query history"):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
