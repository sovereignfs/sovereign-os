import base64
import hashlib
import http.server
import json
import os
import shutil
import ssl
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
EXAMPLE = ROOT / "update/examples/update-manifest-v1.example.json"
OPENSSL = shutil.which("openssl")
ZSTD = shutil.which("zstd")
BUNDLE_BUILDER = ROOT / "scripts/create-update-bundle.py"
APPLIANCE = ROOT / "image-builder/sovereign/appliance"


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
    """Serves real HTTPS with a self-signed certificate: install_available_update
    downloads a real artifact over the network, and validate_manifest requires
    every artifact/notes URL to be HTTPS -- a fake https://example.invalid URL
    (fine for check, which never fetches the artifact) won't do here."""

    def __init__(self, certificate_path, key_path):
        self.server = http.server.HTTPServer(("127.0.0.1", 0), ReleasesHandler)
        self.server.routes = {}
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(certificate_path), keyfile=str(key_path))
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self):
        return f"https://127.0.0.1:{self.server.server_port}"

    def set_route(self, path, body):
        self.server.routes[path] = body

    def stop(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()


@unittest.skipIf(OPENSSL is None or ZSTD is None, "OpenSSL or zstd is unavailable")
class UpdateInstallTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.tls_key = self.directory / "tls-key.pem"
        self.tls_cert = self.directory / "tls-cert.pem"
        subprocess.run(
            [
                # RSA, not Ed25519: the update-bundle download runs through
                # whichever python3 the script's shebang resolves to, which
                # on a dev machine may be an older system Python with a TLS
                # stack that can't negotiate an Ed25519 certificate. RSA is
                # universally supported.
                OPENSSL, "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(self.tls_key), "-out", str(self.tls_cert),
                "-days", "1", "-nodes", "-subj", "/CN=127.0.0.1",
                "-addext", "subjectAltName=IP:127.0.0.1",
            ],
            check=True, capture_output=True,
        )
        self.server = LocalReleasesServer(self.tls_cert, self.tls_key)
        self.addCleanup(self.server.stop)

        self.trust = self.directory / "trust"
        self.trust.mkdir()
        self.release = self.directory / "sovereign-release"
        self.release.write_text('NAME="Sovereign OS"\nVERSION="0.1.0-preview.5"\n')
        self.pihole_env = self.directory / "pihole-image.env"
        self.pihole_env.write_text("PIHOLE_IMAGE_DIGEST=sha256:" + "a" * 64 + "\n")
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
            check=True, capture_output=True,
        )
        subprocess.run(
            [OPENSSL, "pkey", "-in", self.private_key, "-pubout", "-out", self.public_key],
            check=True, capture_output=True,
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

        self.state_root = self.directory / "state"
        (self.state_root / "apps/pihole/etc-pihole").mkdir(parents=True)
        (self.state_root / "apps/pihole/etc-pihole/gravity.db").write_text("fixture")
        (self.state_root / "configuration").mkdir()
        (self.state_root / "configuration/device.json").write_text("{}\n")
        (self.state_root / "secrets").mkdir(mode=0o700)
        (self.state_root / "secrets/pihole-admin-password").write_text("test-only\n")

        self.tools = self.directory / "tools"
        self.tools.mkdir()
        self.service_log = self.directory / "service.log"
        self.systemctl = self.tools / "systemctl"
        self.systemctl.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$SOVEREIGN_TEST_SERVICE_LOG\"\n"
        )
        self.systemctl.chmod(0o755)
        self.health = self.tools / "health"
        self.health.write_text("#!/bin/sh\nexit 0\n")
        self.health.chmod(0o755)
        self.docker = self.tools / "docker"
        self.docker.write_text("#!/bin/sh\nexit 0\n")
        self.docker.chmod(0o755)
        self.nginx = self.tools / "nginx"
        self.nginx.write_text("#!/bin/sh\nexit 0\n")
        self.nginx.chmod(0o755)
        self.tar = self.tools / "tar"
        self.tar.write_text(
            "#!/bin/sh\n"
            "output=\n"
            "previous=\n"
            "for argument in \"$@\"; do\n"
            "  if [ \"$previous\" = --file ]; then output=$argument; fi\n"
            "  previous=$argument\n"
            "done\n"
            "case \" $* \" in\n"
            "  *' --create '*) eval 'last=${'$#'}'; printf '%s/\\n' \"$last\" > \"$output\" ;;\n"
            "  *' --list '*) cat \"$output\" ;;\n"
            "esac\n"
        )
        self.tar.chmod(0o755)

        self.releases = self.directory / "releases"
        active = self.releases / "releases/0.1.0-preview.5"
        active.mkdir(parents=True)
        (active / "sovereign-release").write_text(
            'VERSION="0.1.0-preview.5"\nCHANNEL="preview"\n'
        )
        (active / "pihole-image.env").write_text(self.pihole_env.read_text())
        (self.releases / "current").symlink_to("releases/0.1.0-preview.5")

        self.manifest = json.loads(EXAMPLE.read_text())
        self.manifest["release"]["id"] = "sovereign-os-0.1.0-preview.6"
        self.manifest["release"]["version"] = "0.1.0-preview.6"
        self.manifest["release"]["notes_url"] = "https://example.invalid/notes"
        self.manifest["components"]["appliance"]["version"] = "0.1.0-preview.6"
        self.manifest["compatibility"]["source_versions"] = {
            "minimum": "0.1.0-preview.5",
            "maximum_exclusive": "0.2.0",
        }
        self.manifest["requirements"]["free_bytes"] = 1
        self.manifest["signing"]["key_id"] = "preview-test"

        self.build_update_bundle()

        self.manifest["artifacts"][0]["url"] = f"{self.server.base_url}/bundle.tar.zst"
        self.manifest_path, self.signature_path = self.write_signed_manifest()
        self.server.set_route("/bundle.tar.zst", self.artifact.read_bytes())
        self.server.set_route("/manifest.json", self.manifest_path.read_bytes())
        self.server.set_route("/manifest.sig", self.signature_path.read_bytes())
        self.server.set_route(
            "/releases",
            json.dumps(
                [
                    {
                        "draft": False,
                        "tag_name": "v0.1.0-preview.6",
                        "assets": [
                            {
                                "name": "release-manifest.json",
                                "browser_download_url": f"{self.server.base_url}/manifest.json",
                            },
                            {
                                "name": "release-manifest.sig",
                                "browser_download_url": f"{self.server.base_url}/manifest.sig",
                            },
                        ],
                    }
                ]
            ).encode(),
        )

    def build_update_bundle(self):
        release = self.directory / "target-release"
        release.mkdir()
        shutil.copytree(APPLIANCE, release / "appliance")
        console_index = release / "appliance/console/index.html"
        console_index.write_text(
            console_index.read_text().replace(
                "@SOVEREIGN_RELEASE_VERSION@", "0.1.0-preview.6"
            )
        )
        (release / "sovereign-release").write_text(
            'VERSION="0.1.0-preview.6"\nCHANNEL="preview"\n'
        )
        (release / "pihole-image.env").write_text(
            "PIHOLE_IMAGE_REPOSITORY='docker.io/pihole/pihole'\n"
            "PIHOLE_IMAGE_TAG='2026.04.1'\n"
            f"PIHOLE_IMAGE_DIGEST='{self.manifest['components']['pihole']['digest']}'\n"
            "PIHOLE_IMAGE_PLATFORM='linux/arm64'\n"
        )
        (release / "pihole-arm64.oci.tar").write_bytes(b"OCI fixture\n")
        self.artifact = self.directory / "update-bundle.tar.zst"
        subprocess.run(
            [
                str(BUNDLE_BUILDER),
                "--version", "0.1.0-preview.6",
                "--release-dir", str(release),
                "--output", str(self.artifact),
                "--zstd", ZSTD,
            ],
            check=True, capture_output=True,
        )
        self.manifest["artifacts"][0]["size"] = self.artifact.stat().st_size
        self.manifest["artifacts"][0]["sha256"] = hashlib.sha256(
            self.artifact.read_bytes()
        ).hexdigest()

    def write_signed_manifest(self):
        manifest_path = self.directory / "manifest.json"
        signature_binary = self.directory / "signature.bin"
        signature_path = self.directory / "manifest.sig"
        manifest_path.write_text(json.dumps(self.manifest, separators=(",", ":")) + "\n")
        subprocess.run(
            [
                OPENSSL, "pkeyutl", "-sign", "-inkey", self.private_key,
                "-rawin", "-in", manifest_path, "-out", signature_binary,
            ],
            check=True, capture_output=True,
        )
        signature_path.write_text(base64.b64encode(signature_binary.read_bytes()).decode())
        return manifest_path, signature_path

    def environment(self):
        return os.environ | {
            "SOVEREIGN_UPDATE_POLICY": str(self.policy),
            "SOVEREIGN_RELEASE_PATH": str(self.release),
            "SOVEREIGN_DATA_PATH": str(self.directory),
            "SOVEREIGN_UPDATE_ROOT": str(self.directory / "update-state"),
            "SOVEREIGN_OPENSSL": OPENSSL,
            "SOVEREIGN_PIHOLE_ENV": str(self.pihole_env),
            "SOVEREIGN_STATE_ROOT": str(self.state_root),
            "SOVEREIGN_RELEASES_ROOT": str(self.releases),
            "SOVEREIGN_SYSTEMCTL": str(self.systemctl),
            "SOVEREIGN_UPDATE_HEALTH_CHECK": str(self.health),
            "SOVEREIGN_TAR": str(self.tar),
            "SOVEREIGN_ZSTD": ZSTD,
            "SOVEREIGN_DOCKER": str(self.docker),
            "SOVEREIGN_NGINX": str(self.nginx),
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
            "SOVEREIGN_TEST_SERVICE_LOG": str(self.service_log),
            "SOVEREIGN_UPDATE_CHECK_RELEASES_URL": f"{self.server.base_url}/releases",
            "SOVEREIGN_UPDATE_CHECK_CA_FILE": str(self.tls_cert),
        }

    def run_install(self):
        return subprocess.run(
            [str(CLIENT), "install"],
            env=self.environment(),
            capture_output=True,
            text=True,
        )

    def run_status(self):
        return subprocess.run(
            [str(CLIENT), "status"],
            env=self.environment(),
            capture_output=True,
            text=True,
        )

    def test_install_discovers_downloads_and_commits_the_verified_candidate(self):
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stderr)

        status = self.run_status()
        self.assertEqual(0, status.returncode, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual("0.1.0-preview.6", payload["installed_version"])
        self.assertEqual("committed", payload["update_state"])

    def test_install_fails_closed_when_no_candidate_verifies(self):
        self.server.set_route("/releases", json.dumps([]).encode())
        result = self.run_install()
        self.assertEqual(2, result.returncode)
        self.assertEqual("NO_UPDATE_AVAILABLE", json.loads(result.stderr)["code"])

        status = self.run_status()
        payload = json.loads(status.stdout)
        self.assertEqual("0.1.0-preview.5", payload["installed_version"])
        self.assertEqual("idle", payload["update_state"])

    def test_install_rejects_a_bundle_exceeding_the_size_limit(self):
        environment = self.environment()
        environment["SOVEREIGN_UPDATE_INSTALL_MAX_ARTIFACT_BYTES"] = "10"
        result = subprocess.run(
            [str(CLIENT), "install"], env=environment, capture_output=True, text=True
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual(
            "UPDATE_INSTALL_RESPONSE_TOO_LARGE", json.loads(result.stderr)["code"]
        )


if __name__ == "__main__":
    unittest.main()
