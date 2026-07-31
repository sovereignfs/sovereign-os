import base64
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update"
)
OPENSSL = shutil.which("openssl")


class ReleasesHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = self.server.routes.get(self.path)
        if body is None:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class LocalReleasesServer:
    def __init__(self):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), ReleasesHandler)
        self.server.routes = {}
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def set_route(self, path, body):
        self.server.routes[path] = body

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


@unittest.skipIf(OPENSSL is None, "OpenSSL unavailable")
class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.server = LocalReleasesServer()
        self.addCleanup(self.server.stop)

        self.trust = self.directory / "trust"
        self.trust.mkdir()
        self.release = self.directory / "sovereign-release"
        self.release.write_text('NAME="Sovereign OS"\nVERSION="0.1.0-preview.14"\n')
        self.policy = self.directory / "policy.json"
        self.policy.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "channel": "preview",
                    "device": "rpi5-arm64",
                    "trust_store": str(self.trust),
                }
            )
        )
        self.private_key = self.directory / "private.pem"
        self.public_key = self.trust / "preview-test.pem"
        subprocess.run(
            [OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", self.private_key],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [OPENSSL, "pkey", "-in", self.private_key, "-pubout", "-out", self.public_key],
            check=True,
            capture_output=True,
        )
        (self.trust / "preview-test.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "key_id": "preview-test",
                    "algorithm": "Ed25519",
                    "channels": ["preview"],
                    "revoked": False,
                }
            )
        )
        self.other_private_key = self.directory / "other-private.pem"
        subprocess.run(
            [OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", self.other_private_key],
            check=True,
            capture_output=True,
        )
        self.releases_root = self.directory / "releases"
        (self.releases_root / "releases/0.1.0-preview.14").mkdir(parents=True)
        self.releases_root.joinpath("current").symlink_to("releases/0.1.0-preview.14")

    def tearDown(self):
        self.temporary.cleanup()

    def environment(self):
        return os.environ | {
            "SOVEREIGN_UPDATE_POLICY": str(self.policy),
            "SOVEREIGN_RELEASE_PATH": str(self.release),
            "SOVEREIGN_DATA_PATH": str(self.directory),
            "SOVEREIGN_STATE_ROOT": str(self.directory / "state"),
            "SOVEREIGN_RELEASES_ROOT": str(self.releases_root),
            "SOVEREIGN_UPDATE_ROOT": str(self.directory / "update-state"),
            "SOVEREIGN_OPENSSL": OPENSSL,
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
            "SOVEREIGN_UPDATE_CHECK_RELEASES_URL": f"{self.server.base_url}/releases",
            "SOVEREIGN_UPDATE_CHECK_STATUS": str(self.directory / "state" / "update-check.json"),
        }

    def sign_manifest(self, manifest, private_key=None):
        manifest_path = self.directory / f"manifest-{manifest['release']['version']}.json"
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n")
        signature_binary = self.directory / f"sig-{manifest['release']['version']}.bin"
        subprocess.run(
            [
                OPENSSL, "pkeyutl", "-sign",
                "-inkey", str(private_key or self.private_key),
                "-rawin", "-in", str(manifest_path), "-out", str(signature_binary),
            ],
            check=True,
            capture_output=True,
        )
        signature = base64.b64encode(signature_binary.read_bytes()).decode()
        return manifest_path.read_bytes(), signature.encode()

    def make_manifest(self, version, source_minimum="0.1.0-preview.13", channel="preview", key_id="preview-test"):
        artifact_bytes = f"fixture-{version}".encode()
        return {
            "schema_version": 1,
            "release": {
                "id": f"sovereign-os-{version}",
                "version": version,
                "published_at": "2026-08-01T00:00:00Z",
                "channel": channel,
                "notes_url": f"https://example.invalid/notes/{version}",
            },
            "compatibility": {
                "devices": ["rpi5-arm64"],
                "source_versions": {"minimum": source_minimum, "maximum_exclusive": "0.2.0"},
                "allow_downgrade": False,
            },
            "artifacts": [{
                "role": "update_bundle",
                "url": f"https://example.invalid/{version}.tar.zst",
                "size": len(artifact_bytes),
                "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
                "media_type": "application/vnd.sovereign.update.v1+tar+zstd",
            }],
            "components": {
                "appliance": {"version": version},
                "image_base": {"version": source_minimum},
                "pihole": {"version": "2026.04.1", "repository": "docker.io/pihole/pihole", "digest": "sha256:" + "a" * 64},
            },
            "requirements": {"free_bytes": 1, "reboot": False},
            "migrations": [],
            "rollback": {"supported": True, "requires_data_restore": False, "limitations": []},
            "signing": {"algorithm": "Ed25519", "key_id": key_id},
        }

    def add_release(self, version, tag=None, draft=False, manifest=None, signature=None, include_sig=True):
        tag = tag or f"v{version}"
        assets = [{
            "name": "release-manifest.json",
            "browser_download_url": f"{self.server.base_url}/assets/{version}/release-manifest.json",
        }]
        if include_sig:
            assets.append({
                "name": "release-manifest.sig",
                "browser_download_url": f"{self.server.base_url}/assets/{version}/release-manifest.sig",
            })
        if manifest is not None:
            self.server.set_route(f"/assets/{version}/release-manifest.json", manifest)
        if signature is not None:
            self.server.set_route(f"/assets/{version}/release-manifest.sig", signature)
        return {"draft": draft, "tag_name": tag, "assets": assets}

    def run_check(self):
        return subprocess.run(
            [str(CLIENT), "check"], env=self.environment(), capture_output=True, text=True
        )

    def test_no_releases_reports_up_to_date(self):
        self.server.set_route("/releases", b"[]")
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("up_to_date", status["status"])
        self.assertEqual("0.1.0-preview.14", status["current_version"])
        self.assertIsNone(status["available_version"])
        self.assertIsNone(status["error"])

    def test_only_draft_releases_are_ignored(self):
        release = self.add_release("0.1.0-preview.15", draft=True)
        manifest, signature = self.sign_manifest(self.make_manifest("0.1.0-preview.15"))
        self.server.set_route("/assets/0.1.0-preview.15/release-manifest.json", manifest)
        self.server.set_route("/assets/0.1.0-preview.15/release-manifest.sig", signature)
        self.server.set_route("/releases", json.dumps([release]).encode())
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("up_to_date", status["status"])

    def test_compatible_signed_release_is_reported_available(self):
        manifest_dict = self.make_manifest("0.1.0-preview.15")
        manifest, signature = self.sign_manifest(manifest_dict)
        release = self.add_release("0.1.0-preview.15", manifest=manifest, signature=signature)
        self.server.set_route("/releases", json.dumps([release]).encode())
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("update_available", status["status"])
        self.assertEqual("0.1.0-preview.15", status["available_version"])
        self.assertEqual("0.1.0-preview.14", status["current_version"])
        self.assertEqual("preview", status["channel"])
        self.assertEqual("https://example.invalid/notes/0.1.0-preview.15", status["notes_url"])
        self.assertFalse(status["reboot_required"])
        self.assertIsNone(status["error"])
        check_path = self.directory / "state" / "update-check.json"
        self.assertTrue(check_path.is_file())
        self.assertEqual(0o644, check_path.stat().st_mode & 0o777)
        self.assertEqual(status, json.loads(check_path.read_text()))

    def test_falls_back_past_a_badly_signed_higher_version(self):
        bad_manifest, bad_signature = self.sign_manifest(
            self.make_manifest("0.1.0-preview.16"), private_key=self.other_private_key
        )
        bad_release = self.add_release("0.1.0-preview.16", manifest=bad_manifest, signature=bad_signature)
        good_manifest, good_signature = self.sign_manifest(self.make_manifest("0.1.0-preview.15"))
        good_release = self.add_release("0.1.0-preview.15", manifest=good_manifest, signature=good_signature)
        self.server.set_route("/releases", json.dumps([bad_release, good_release]).encode())
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("update_available", status["status"])
        self.assertEqual("0.1.0-preview.15", status["available_version"])

    def test_wrong_channel_release_is_skipped_and_reported(self):
        manifest, signature = self.sign_manifest(self.make_manifest("0.1.0-preview.15", channel="stable"))
        release = self.add_release("0.1.0-preview.15", manifest=manifest, signature=signature)
        self.server.set_route("/releases", json.dumps([release]).encode())
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("up_to_date", status["status"])
        # The trusted key itself is only scoped to "preview", so that check
        # fires before the manifest's own declared channel is compared.
        self.assertEqual("WRONG_KEY_CHANNEL", status["error"])

    def test_downgrade_candidate_is_skipped(self):
        manifest, signature = self.sign_manifest(self.make_manifest("0.1.0-preview.10"))
        release = self.add_release("0.1.0-preview.10", manifest=manifest, signature=signature)
        self.server.set_route("/releases", json.dumps([release]).encode())
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("up_to_date", status["status"])
        self.assertEqual("DOWNGRADE_REJECTED", status["error"])

    def test_release_missing_signature_asset_is_skipped(self):
        release = self.add_release("0.1.0-preview.15", include_sig=False)
        self.server.set_route("/releases", json.dumps([release]).encode())
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("up_to_date", status["status"])

    def test_oversized_response_reports_check_failed(self):
        self.server.set_route("/releases", b"[" + b"0" * (3 * 1024 * 1024) + b"]")
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("check_failed", status["status"])
        self.assertEqual("UPDATE_CHECK_RESPONSE_TOO_LARGE", status["error"])

    def test_malformed_json_reports_check_failed(self):
        self.server.set_route("/releases", b"not json")
        completed = self.run_check()
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("check_failed", status["status"])
        self.assertEqual("UPDATE_CHECK_INVALID_RESPONSE", status["error"])

    def test_unreachable_endpoint_reports_check_failed(self):
        environment = self.environment() | {
            "SOVEREIGN_UPDATE_CHECK_RELEASES_URL": "http://127.0.0.1:1/releases",
        }
        completed = subprocess.run(
            [str(CLIENT), "check"], env=environment, capture_output=True, text=True
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("check_failed", status["status"])
        self.assertEqual("UPDATE_CHECK_NETWORK_FAILED", status["error"])

    def test_status_reflects_check_result(self):
        completed = subprocess.run(
            [str(CLIENT), "status"], env=self.environment(), capture_output=True, text=True
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIsNone(json.loads(completed.stdout)["update_check"])

        manifest, signature = self.sign_manifest(self.make_manifest("0.1.0-preview.15"))
        release = self.add_release("0.1.0-preview.15", manifest=manifest, signature=signature)
        self.server.set_route("/releases", json.dumps([release]).encode())
        checked = self.run_check()
        self.assertEqual(0, checked.returncode, checked.stderr)

        completed = subprocess.run(
            [str(CLIENT), "status"], env=self.environment(), capture_output=True, text=True
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        status = json.loads(completed.stdout)
        self.assertEqual("update_available", status["update_check"]["status"])
        self.assertEqual("0.1.0-preview.15", status["update_check"]["available_version"])

    def test_check_requires_root(self):
        environment = self.environment() | {"SOVEREIGN_UPDATE_TEST_MODE": "0"}
        completed = subprocess.run(
            [str(CLIENT), "check"], env=environment, capture_output=True, text=True
        )
        self.assertEqual(2, completed.returncode)
        self.assertEqual("ROOT_REQUIRED", json.loads(completed.stderr)["code"])


if __name__ == "__main__":
    unittest.main()
