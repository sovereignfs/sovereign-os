import base64
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
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
TAR = shutil.which("tar")


@unittest.skipIf(
    OPENSSL is None or ZSTD is None or TAR is None,
    "OpenSSL, zstd, or tar is unavailable",
)
class UpdateRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
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
        (self.state_root / "secrets/pihole-admin-password").chmod(0o600)
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
            "SOVEREIGN_ZSTD": ZSTD,
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
            "SOVEREIGN_TEST_SERVICE_LOG": str(self.service_log),
            "COPYFILE_DISABLE": "1",
        }

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
            check=True,
            capture_output=True,
        )
        signature_path.write_text(base64.b64encode(signature_binary.read_bytes()).decode())
        return manifest_path, signature_path

    def run_client(self, *arguments, env=None):
        return subprocess.run(
            [str(CLIENT), *arguments],
            env=env or self.environment(),
            capture_output=True,
            text=True,
        )

    def create_backup(self):
        manifest, signature = self.write_signed_manifest()
        prepared = self.run_client(
            "prepare", "--manifest", str(manifest), "--signature", str(signature),
            "--artifact", str(self.artifact),
        )
        self.assertEqual(0, prepared.returncode, prepared.stderr)
        transaction_id = json.loads(prepared.stdout)["transaction_id"]
        backed_up = self.run_client("backup", transaction_id)
        self.assertEqual(0, backed_up.returncode, backed_up.stderr)
        return json.loads(backed_up.stdout)["backup_id"]

    def corrupt_live_data(self):
        (self.state_root / "apps/pihole/etc-pihole/gravity.db").write_text("corrupted")
        (self.state_root / "configuration/device.json").write_text("{\"corrupted\":true}\n")
        (self.state_root / "secrets/pihole-admin-password").write_text("corrupted\n")

    def assertOriginalDataRestored(self):
        self.assertEqual(
            "fixture", (self.state_root / "apps/pihole/etc-pihole/gravity.db").read_text()
        )
        self.assertEqual(
            "{}\n", (self.state_root / "configuration/device.json").read_text()
        )
        secret = self.state_root / "secrets/pihole-admin-password"
        self.assertEqual("test-only\n", secret.read_text())
        self.assertEqual(0o600, secret.stat().st_mode & 0o777)
        self.assertEqual(
            0o700, (self.state_root / "secrets").stat().st_mode & 0o777
        )

    def test_restore_recovers_original_data_and_commits(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        self.service_log.write_text("")
        restored = self.run_client("restore", backup_id)
        self.assertEqual(0, restored.returncode, restored.stderr)
        result = json.loads(restored.stdout)
        self.assertEqual("committed", result["status"])
        self.assertEqual(backup_id, result["backup_id"])
        self.assertOriginalDataRestored()
        state = json.loads(
            (self.directory / "update-state/restores" / result["restore_id"] / "state.json").read_text()
        )
        self.assertEqual("committed", state["state"])
        self.assertFalse(
            (self.directory / "update-state/restores" / result["restore_id"] / "restore-candidate").exists()
        )
        remaining = list(self.state_root.glob("*/.pre-restore.*")) + list(
            self.state_root.glob(".*.pre-restore.*")
        )
        self.assertEqual([], remaining)
        self.assertEqual(
            ["stop sovereign-pihole.service", "start sovereign-pihole.service"],
            self.service_log.read_text().splitlines(),
        )

    def test_restore_rejects_version_mismatch_without_force(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        newer = self.releases / "releases/0.1.0-preview.6"
        newer.mkdir(parents=True)
        (newer / "sovereign-release").write_text(
            'VERSION="0.1.0-preview.6"\nCHANNEL="preview"\n'
        )
        (self.releases / "current").unlink()
        (self.releases / "current").symlink_to("releases/0.1.0-preview.6")
        restored = self.run_client("restore", backup_id)
        self.assertEqual(2, restored.returncode)
        self.assertEqual("RESTORE_VERSION_MISMATCH", json.loads(restored.stderr)["code"])
        self.assertEqual(
            "corrupted", (self.state_root / "apps/pihole/etc-pihole/gravity.db").read_text()
        )

    def test_restore_accepts_version_mismatch_with_force(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        newer = self.releases / "releases/0.1.0-preview.6"
        newer.mkdir(parents=True)
        (newer / "sovereign-release").write_text(
            'VERSION="0.1.0-preview.6"\nCHANNEL="preview"\n'
        )
        (self.releases / "current").unlink()
        (self.releases / "current").symlink_to("releases/0.1.0-preview.6")
        restored = self.run_client("restore", backup_id, "--force")
        self.assertEqual(0, restored.returncode, restored.stderr)
        self.assertOriginalDataRestored()

    def test_restore_rejects_tampered_archive_before_touching_live_data(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        archive = self.state_root / "backups" / backup_id / "pihole-state.tar.zst"
        archive.write_bytes(archive.read_bytes() + b"tampered")
        restored = self.run_client("restore", backup_id)
        self.assertEqual(2, restored.returncode)
        self.assertIn(
            json.loads(restored.stderr)["code"],
            {"ARTIFACT_SIZE_MISMATCH", "ARTIFACT_DIGEST_MISMATCH"},
        )
        self.assertEqual(
            "corrupted", (self.state_root / "apps/pihole/etc-pihole/gravity.db").read_text()
        )
        self.assertEqual(
            [], list((self.directory / "update-state/restores").glob("*"))
        )

    def test_restore_rejects_path_traversal_in_archive(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        malicious_dir = self.directory / "malicious"
        (malicious_dir / "etc-pihole").mkdir(parents=True)
        tar_path = self.directory / "malicious.tar"
        with tarfile.open(tar_path, "w") as archive:
            info = tarfile.TarInfo("etc-pihole/../../etc/passwd")
            payload = b"unsafe\n"
            info.size = len(payload)
            info.mode = 0o644
            import io

            archive.addfile(info, io.BytesIO(payload))
        malicious_archive = self.state_root / "backups" / backup_id / "pihole-state.tar.zst"
        subprocess.run(
            [ZSTD, "--force", "--quiet", str(tar_path), "-o", str(malicious_archive)],
            check=True,
        )
        manifest_path = self.state_root / "backups" / backup_id / "backup-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        digest = hashlib.sha256(malicious_archive.read_bytes()).hexdigest()
        size = malicious_archive.stat().st_size
        for artifact in manifest["artifacts"]:
            if artifact["role"] == "pihole_state":
                artifact["sha256"] = digest
                artifact["size"] = size
        manifest_path.write_text(json.dumps(manifest))
        restored = self.run_client("restore", backup_id)
        self.assertEqual(2, restored.returncode)
        self.assertEqual("BACKUP_ARCHIVE_UNSAFE", json.loads(restored.stderr)["code"])
        self.assertEqual(
            "corrupted", (self.state_root / "apps/pihole/etc-pihole/gravity.db").read_text()
        )

    def test_restore_rolls_back_on_post_restore_health_failure(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        marker = self.directory / "health-fail-once"
        self.health.write_text(
            "#!/bin/sh\n"
            f"if [ ! -f '{marker}' ]; then touch '{marker}'; exit 1; fi\n"
            "exit 0\n"
        )
        restored = self.run_client("restore", backup_id)
        self.assertEqual(2, restored.returncode)
        self.assertEqual("POSTRESTORE_HEALTH_FAILED", json.loads(restored.stderr)["code"])
        self.assertEqual(
            "corrupted", (self.state_root / "apps/pihole/etc-pihole/gravity.db").read_text()
        )
        restores = list((self.directory / "update-state/restores").glob("*/state.json"))
        self.assertEqual(1, len(restores))
        state = json.loads(restores[0].read_text())
        self.assertEqual("rolled_back", state["state"])
        remaining = list(self.state_root.glob(".*.rollback-failed.*"))
        self.assertEqual([], remaining)

    def test_qualification_forced_failure_uses_restore_specific_code(self):
        # SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH is shared with the update
        # transaction flow; the reported failure code must still identify
        # this as a restore failure, not an update failure, for accurate
        # qualification evidence.
        backup_id = self.create_backup()
        self.corrupt_live_data()
        environment = self.environment() | {
            "SOVEREIGN_UPDATE_QUALIFICATION": "1",
            "SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH": "1",
        }
        restored = self.run_client("restore", backup_id, env=environment)
        self.assertEqual(2, restored.returncode)
        self.assertEqual("POSTRESTORE_HEALTH_FAILED", json.loads(restored.stderr)["code"])
        restores = list((self.directory / "update-state/restores").glob("*/state.json"))
        state = json.loads(restores[0].read_text())
        self.assertEqual("rolled_back", state["state"])
        self.assertEqual("POSTRESTORE_HEALTH_FAILED", state["failure"]["code"])

    def test_restore_reaches_recovery_required_when_rollback_health_also_fails(self):
        # When rollback's own health check also fails, the updater must retain
        # both trees rather than guess: the pre-restore state stays live (it
        # was never proven unhealthy on its own), and the rejected restored
        # candidate is kept aside under a `.rollback-failed.` name for manual
        # inspection instead of being deleted.
        backup_id = self.create_backup()
        self.corrupt_live_data()
        self.health.write_text("#!/bin/sh\nexit 1\n")
        restored = self.run_client("restore", backup_id)
        self.assertEqual(2, restored.returncode)
        restores = list((self.directory / "update-state/restores").glob("*/state.json"))
        self.assertEqual(1, len(restores))
        state = json.loads(restores[0].read_text())
        self.assertEqual("recovery_required", state["state"])
        self.assertEqual("manual", state["recovery_action"])
        self.assertEqual(
            "corrupted", (self.state_root / "apps/pihole/etc-pihole/gravity.db").read_text()
        )
        failed = list(self.state_root.glob("apps/pihole/etc-pihole.rollback-failed.*"))
        self.assertEqual(1, len(failed))
        self.assertEqual("fixture", (failed[0] / "gravity.db").read_text())

    def test_discard_restore_rejects_committed_restore(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        restored = self.run_client("restore", backup_id)
        self.assertEqual(0, restored.returncode, restored.stderr)
        restore_id = json.loads(restored.stdout)["restore_id"]
        discarded = self.run_client("discard-restore", restore_id)
        self.assertEqual(2, discarded.returncode)
        self.assertEqual("INVALID_RESTORE_STATE", json.loads(discarded.stderr)["code"])

    def test_discard_restore_marks_recovery_required_discarded(self):
        backup_id = self.create_backup()
        self.corrupt_live_data()
        self.health.write_text("#!/bin/sh\nexit 1\n")
        restored = self.run_client("restore", backup_id)
        self.assertEqual(2, restored.returncode)
        restore_id = json.loads(
            (list((self.directory / "update-state/restores").glob("*/state.json"))[0]).read_text()
        )["restore_id"]
        discarded = self.run_client("discard-restore", restore_id)
        self.assertEqual(0, discarded.returncode, discarded.stderr)
        state = json.loads(
            (self.directory / "update-state/restores" / restore_id / "state.json").read_text()
        )
        self.assertEqual("discarded", state["state"])


if __name__ == "__main__":
    unittest.main()
