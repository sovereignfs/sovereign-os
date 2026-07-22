import base64
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
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


@unittest.skipIf(OPENSSL is None or ZSTD is None, "OpenSSL or zstd is unavailable")
class UpdateClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.trust = self.directory / "trust"
        self.trust.mkdir()
        self.release = self.directory / "sovereign-release"
        self.release.write_text('NAME="Sovereign OS"\nVERSION="0.1.0-preview.5"\n')
        self.pihole_env = self.directory / "pihole-image.env"
        self.pihole_env.write_text(
            "PIHOLE_IMAGE_DIGEST=sha256:"
            + "a" * 64
            + "\n"
        )
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
        self.artifact = self.directory / "update.tar.zst"
        self.artifact.write_bytes(b"authenticated update fixture\n")
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
        self.manifest["components"]["appliance"]["version"] = "0.1.0-preview.6"
        self.manifest["compatibility"]["source_versions"] = {
            "minimum": "0.1.0-preview.5",
            "maximum_exclusive": "0.2.0",
        }
        self.manifest["requirements"]["free_bytes"] = 1
        self.manifest["signing"]["key_id"] = "preview-test"
        self.manifest["artifacts"][0]["size"] = self.artifact.stat().st_size
        self.manifest["artifacts"][0]["sha256"] = hashlib.sha256(
            self.artifact.read_bytes()
        ).hexdigest()

    def tearDown(self):
        self.temporary.cleanup()

    def write_signed_manifest(self, manifest=None):
        manifest_path = self.directory / "manifest.json"
        signature_binary = self.directory / "signature.bin"
        signature_path = self.directory / "manifest.sig"
        manifest_path.write_text(
            json.dumps(manifest or self.manifest, separators=(",", ":")) + "\n"
        )
        subprocess.run(
            [
                OPENSSL,
                "pkeyutl",
                "-sign",
                "-inkey",
                self.private_key,
                "-rawin",
                "-in",
                manifest_path,
                "-out",
                signature_binary,
            ],
            check=True,
            capture_output=True,
        )
        signature_path.write_text(base64.b64encode(signature_binary.read_bytes()).decode())
        return manifest_path, signature_path

    def run_client(self, manifest, signature, artifact=True):
        environment = os.environ | {
            "SOVEREIGN_UPDATE_POLICY": str(self.policy),
            "SOVEREIGN_RELEASE_PATH": str(self.release),
            "SOVEREIGN_DATA_PATH": str(self.directory),
            "SOVEREIGN_UPDATE_ROOT": str(self.directory / "update-state"),
            "SOVEREIGN_OPENSSL": OPENSSL,
            "SOVEREIGN_PIHOLE_ENV": str(self.pihole_env),
        }
        command = [
            str(CLIENT),
            "inspect",
            "--manifest",
            str(manifest),
            "--signature",
            str(signature),
        ]
        if artifact:
            command.extend(["--artifact", str(self.artifact)])
        return subprocess.run(command, env=environment, capture_output=True, text=True)

    def run_prepare(self, manifest, signature):
        environment = self.environment()
        return subprocess.run(
            [
                str(CLIENT),
                "prepare",
                "--manifest",
                str(manifest),
                "--signature",
                str(signature),
                "--artifact",
                str(self.artifact),
            ],
            env=environment,
            capture_output=True,
            text=True,
        )

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
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
            "SOVEREIGN_TEST_SERVICE_LOG": str(self.service_log),
        }

    def build_update_bundle(self):
        release = self.directory / "target-release"
        release.mkdir()
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
                "--version",
                "0.1.0-preview.6",
                "--release-dir",
                str(release),
                "--output",
                str(self.artifact),
                "--zstd",
                ZSTD,
            ],
            check=True,
            capture_output=True,
        )
        self.manifest["artifacts"][0]["size"] = self.artifact.stat().st_size
        self.manifest["artifacts"][0]["sha256"] = hashlib.sha256(
            self.artifact.read_bytes()
        ).hexdigest()

    def test_accepts_trusted_compatible_manifest_and_artifact(self):
        manifest, signature = self.write_signed_manifest()
        completed = self.run_client(manifest, signature)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("verified", result["status"])
        self.assertTrue(result["artifact_verified"])
        self.assertEqual("0.1.0-preview.6", result["target_version"])

    def test_rejects_manifest_changed_after_signing(self):
        manifest, signature = self.write_signed_manifest()
        manifest.write_bytes(manifest.read_bytes().replace(b"preview.6", b"preview.7"))
        completed = self.run_client(manifest, signature)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("SIGNATURE_MISMATCH", json.loads(completed.stderr)["code"])

    def test_rejects_corrupt_artifact(self):
        manifest, signature = self.write_signed_manifest()
        self.artifact.write_bytes(b"corrupt but same size........\n")
        completed = self.run_client(manifest, signature)
        self.assertEqual(2, completed.returncode)
        self.assertIn(
            json.loads(completed.stderr)["code"],
            {"ARTIFACT_SIZE_MISMATCH", "ARTIFACT_DIGEST_MISMATCH"},
        )

    def test_rejects_wrong_device_after_authentication(self):
        self.manifest["compatibility"]["devices"] = []
        manifest, signature = self.write_signed_manifest()
        completed = self.run_client(manifest, signature, artifact=False)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("INVALID_MANIFEST", json.loads(completed.stderr)["code"])

    def test_rejects_downgrade(self):
        self.manifest["release"]["version"] = "0.1.0-preview.4"
        self.manifest["components"]["appliance"]["version"] = "0.1.0-preview.4"
        manifest, signature = self.write_signed_manifest()
        completed = self.run_client(manifest, signature, artifact=False)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("DOWNGRADE_REJECTED", json.loads(completed.stderr)["code"])

    def test_rejects_revoked_key(self):
        metadata = json.loads((self.trust / "preview-test.json").read_text())
        metadata["revoked"] = True
        (self.trust / "preview-test.json").write_text(json.dumps(metadata))
        manifest, signature = self.write_signed_manifest()
        completed = self.run_client(manifest, signature, artifact=False)
        self.assertEqual(2, completed.returncode)
        self.assertEqual("REVOKED_SIGNING_KEY", json.loads(completed.stderr)["code"])

    def test_prepare_creates_durable_verified_transaction(self):
        manifest, signature = self.write_signed_manifest()
        completed = self.run_prepare(manifest, signature)
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        transaction = (
            self.directory
            / "update-state/transactions"
            / result["transaction_id"]
        )
        state = json.loads((transaction / "state.json").read_text())
        events = [json.loads(line) for line in (transaction / "events.jsonl").read_text().splitlines()]
        self.assertEqual("verified", state["state"])
        self.assertEqual(2, state["sequence"])
        self.assertEqual(
            ["available", "downloading", "verified"],
            [event["next_state"] for event in events],
        )
        self.assertEqual(self.artifact.read_bytes(), (transaction / "staging/update-bundle.tar.zst").read_bytes())
        self.assertEqual(0o600, (transaction / "state.json").stat().st_mode & 0o777)

    def test_failed_prepare_does_not_reach_verified(self):
        manifest, signature = self.write_signed_manifest()
        self.artifact.write_bytes(b"corrupt")
        completed = self.run_prepare(manifest, signature)
        self.assertEqual(2, completed.returncode)
        transactions = list((self.directory / "update-state/transactions").glob("*"))
        self.assertEqual([], transactions)

    def test_backup_is_complete_and_health_gated(self):
        manifest, signature = self.write_signed_manifest()
        prepared = self.run_prepare(manifest, signature)
        transaction_id = json.loads(prepared.stdout)["transaction_id"]
        completed = subprocess.run(
            [str(CLIENT), "backup", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        backup = self.state_root / "backups" / result["backup_id"]
        backup_manifest = json.loads((backup / "backup-manifest.json").read_text())
        self.assertEqual(
            {"pihole_state", "sovereign_configuration", "secrets", "release_pointer"},
            {artifact["role"] for artifact in backup_manifest["artifacts"]},
        )
        state = json.loads(
            (
                self.directory
                / "update-state/transactions"
                / transaction_id
                / "state.json"
            ).read_text()
        )
        self.assertEqual("backed_up", state["state"])
        self.assertEqual(result["backup_id"], state["backup_id"])
        self.assertEqual(
            ["stop sovereign-pihole.service", "start sovereign-pihole.service"],
            self.service_log.read_text().splitlines(),
        )

    def test_failed_post_backup_health_requires_recovery(self):
        manifest, signature = self.write_signed_manifest()
        prepared = self.run_prepare(manifest, signature)
        transaction_id = json.loads(prepared.stdout)["transaction_id"]
        self.health.write_text("#!/bin/sh\nexit 1\n")
        completed = subprocess.run(
            [str(CLIENT), "backup", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, completed.returncode)
        state = json.loads(
            (
                self.directory
                / "update-state/transactions"
                / transaction_id
                / "state.json"
            ).read_text()
        )
        self.assertEqual("recovery_required", state["state"])
        self.assertEqual("PREUPDATE_HEALTH_FAILED", state["failure"]["code"])

    def prepare_and_backup_bundle(self):
        self.build_update_bundle()
        manifest, signature = self.write_signed_manifest()
        prepared = self.run_prepare(manifest, signature)
        self.assertEqual(0, prepared.returncode, prepared.stderr)
        transaction_id = json.loads(prepared.stdout)["transaction_id"]
        backed_up = subprocess.run(
            [str(CLIENT), "backup", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, backed_up.returncode, backed_up.stderr)
        return transaction_id

    def test_stage_and_activate_commits_versioned_release(self):
        transaction_id = self.prepare_and_backup_bundle()
        staged = subprocess.run(
            [str(CLIENT), "stage", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, staged.returncode, staged.stderr)
        activated = subprocess.run(
            [str(CLIENT), "activate", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, activated.returncode, activated.stderr)
        self.assertEqual("0.1.0-preview.6", self.releases.joinpath("current").resolve().name)
        self.assertFalse(
            (self.releases / "releases/0.1.0-preview.6/pihole-arm64.oci.tar").exists()
        )
        self.assertFalse(
            (
                self.directory
                / "update-state/transactions"
                / transaction_id
                / "release-candidate"
            ).exists()
        )
        state = json.loads(
            (self.directory / "update-state/transactions" / transaction_id / "state.json").read_text()
        )
        self.assertEqual("committed", state["state"])

    def test_failed_activation_health_rolls_back_pointer(self):
        transaction_id = self.prepare_and_backup_bundle()
        staged = subprocess.run(
            [str(CLIENT), "stage", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, staged.returncode, staged.stderr)
        health_marker = self.directory / "health-failed-once"
        self.health.write_text(
            "#!/bin/sh\n"
            f"if [ ! -f '{health_marker}' ]; then touch '{health_marker}'; exit 1; fi\n"
            "exit 0\n"
        )
        activated = subprocess.run(
            [str(CLIENT), "activate", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, activated.returncode)
        self.assertEqual("0.1.0-preview.5", self.releases.joinpath("current").resolve().name)
        state = json.loads(
            (self.directory / "update-state/transactions" / transaction_id / "state.json").read_text()
        )
        self.assertEqual("rolled_back", state["state"])


if __name__ == "__main__":
    unittest.main()
