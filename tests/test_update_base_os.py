import base64
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update"
)
OPENSSL = shutil.which("openssl")

_TEMP_FOR_IMPORT = tempfile.TemporaryDirectory()
os.environ.setdefault("SOVEREIGN_UPDATE_TEST_MODE", "1")
os.environ.setdefault("SOVEREIGN_BASE_OS_RELEASE_PATH", str(Path(_TEMP_FOR_IMPORT.name) / "base-os-release"))
Path(os.environ["SOVEREIGN_BASE_OS_RELEASE_PATH"]).write_text('VERSION="0.1.0-proof.1"\n')
SPEC = importlib.util.spec_from_loader("sovereign_update", SourceFileLoader("sovereign_update", str(CLIENT)))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BaseOsManifestValidationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {
            "schema_version": 1,
            "release": {
                "id": "sovereign-os-base-0.1.0-proof.2",
                "version": "0.1.0-proof.2",
                "published_at": "2026-08-02T00:00:00Z",
                "channel": "preview",
                "notes_url": "https://example.invalid/notes",
            },
            "compatibility": {
                "devices": ["rpi5-arm64"],
                "source_versions": {"minimum": "0.1.0-proof.1", "maximum_exclusive": "0.2.0"},
                "allow_downgrade": False,
            },
            "artifacts": [
                {
                    "role": "system_boot",
                    "url": "https://example.invalid/boot.img",
                    "size": 1024,
                    "sha256": "a" * 64,
                    "media_type": MODULE.BASE_OS_BOOT_MEDIA_TYPE,
                },
                {
                    "role": "system_root",
                    "url": "https://example.invalid/root.img",
                    "size": 2048,
                    "sha256": "b" * 64,
                    "media_type": MODULE.BASE_OS_ROOT_MEDIA_TYPE,
                },
            ],
            "components": {"image_base": {"version": "0.1.0-proof.2"}},
            "requirements": {"free_bytes": 1024, "reboot": True},
            "rollback": {"supported": True, "requires_data_restore": False, "limitations": ["Must reflash to move to an older base-OS version."]},
            "signing": {"algorithm": "Ed25519", "key_id": "preview-test"},
        }

    def test_accepts_a_well_formed_manifest(self):
        by_role = MODULE.validate_base_os_manifest(self.manifest)
        self.assertEqual({"system_boot", "system_root"}, set(by_role))

    def test_rejects_a_single_artifact(self):
        self.manifest["artifacts"] = self.manifest["artifacts"][:1]
        with self.assertRaises(MODULE.UpdateError):
            MODULE.validate_base_os_manifest(self.manifest)

    def test_rejects_wrong_artifact_roles(self):
        self.manifest["artifacts"][0]["role"] = "update_bundle"
        with self.assertRaises(MODULE.UpdateError):
            MODULE.validate_base_os_manifest(self.manifest)

    def test_rejects_wrong_media_type(self):
        self.manifest["artifacts"][0]["media_type"] = "application/octet-stream"
        with self.assertRaises(MODULE.UpdateError):
            MODULE.validate_base_os_manifest(self.manifest)

    def test_requires_reboot_true(self):
        self.manifest["requirements"]["reboot"] = False
        with self.assertRaises(MODULE.UpdateError):
            MODULE.validate_base_os_manifest(self.manifest)

    def test_rejects_downgrade_allowed(self):
        self.manifest["compatibility"]["allow_downgrade"] = True
        with self.assertRaises(MODULE.UpdateError):
            MODULE.validate_base_os_manifest(self.manifest)

    def test_rejects_component_version_mismatch(self):
        self.manifest["components"]["image_base"]["version"] = "9.9.9"
        with self.assertRaises(MODULE.UpdateError):
            MODULE.validate_base_os_manifest(self.manifest)


class BaseOsSlotSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_refuses_when_other_resolves_to_the_active_device(self):
        shared = self.directory / "same-device"
        shared.write_bytes(b"x")
        other = self.directory / "other-link"
        active = self.directory / "active-link"
        other.symlink_to(shared)
        active.symlink_to(shared)
        with self.assertRaises(MODULE.UpdateError) as caught:
            MODULE.assert_writable_other_slot_device(other, active, "boot")
        self.assertEqual("REFUSING_ACTIVE_SLOT_WRITE", caught.exception.code)

    def test_accepts_distinct_other_and_active_devices(self):
        other_target = self.directory / "system-b"
        other_target.write_bytes(b"x")
        active_target = self.directory / "system-a"
        active_target.write_bytes(b"y")
        other = self.directory / "other-link"
        active = self.directory / "active-link"
        other.symlink_to(other_target)
        active.symlink_to(active_target)
        resolved = MODULE.assert_writable_other_slot_device(other, active, "boot")
        self.assertEqual(other_target.resolve(), resolved)

    def test_rejects_a_missing_other_device(self):
        with self.assertRaises(MODULE.UpdateError) as caught:
            MODULE.assert_writable_other_slot_device(
                self.directory / "does-not-exist", self.directory / "also-missing", "root"
            )
        self.assertEqual("SLOT_DEVICE_MISSING", caught.exception.code)


@unittest.skipIf(OPENSSL is None, "OpenSSL is unavailable")
class BaseOsTransactionFlowTests(unittest.TestCase):
    """Exercises stage-base-os / trial-base-os / verify-base-os-trial /
    commit-base-os as a real subprocess pipeline, mirroring the fixture
    pattern used for the appliance install flow (test_update_install.py):
    real Ed25519 signing, real files standing in for the boot/root
    artifacts and the "other slot" block devices, stub reboot/health-check
    scripts instead of a real reboot or a real Docker/DNS/HTTP check."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

        self.trust = self.directory / "trust"
        self.trust.mkdir()
        self.private_key = self.directory / "private.pem"
        self.public_key = self.trust / "preview-test.pem"
        subprocess.run([OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", self.private_key], check=True, capture_output=True)
        subprocess.run([OPENSSL, "pkey", "-in", self.private_key, "-pubout", "-out", self.public_key], check=True, capture_output=True)
        (self.trust / "preview-test.json").write_text(json.dumps({
            "schema_version": 1, "key_id": "preview-test", "algorithm": "Ed25519",
            "channels": ["preview"], "revoked": False,
        }))

        self.policy = self.directory / "policy.json"
        self.policy.write_text(json.dumps({
            "schema_version": 1, "channel": "preview", "device": "rpi5-arm64", "trust_store": str(self.trust),
        }))

        self.base_os_release = self.directory / "sovereign-base-os-release"
        self.base_os_release.write_text('VERSION="0.1.0-proof.1"\n')
        self.release = self.directory / "sovereign-release"
        self.release.write_text('VERSION="0.1.0-preview.5"\n')

        self.data_path = self.directory / "data"
        self.data_path.mkdir()
        self.state_root = self.directory / "state"
        self.state_root.mkdir()

        # Stand-ins for the by-slot symlinks and their targets: "other"
        # points at a genuinely different file than "active", the same
        # safety-relevant shape as the real udev-provided symlinks.
        self.active_boot_target = self.directory / "active-boot.img"
        self.active_boot_target.write_bytes(b"active boot\n")
        self.active_system_target = self.directory / "active-system.img"
        self.active_system_target.write_bytes(b"active system\n")
        self.other_boot_target = self.directory / "other-boot.img"
        self.other_boot_target.touch()
        self.other_system_target = self.directory / "other-system.img"
        self.other_system_target.touch()
        self.active_boot_link = self.directory / "active-boot-link"
        self.active_boot_link.symlink_to(self.active_boot_target)
        self.active_system_link = self.directory / "active-system-link"
        self.active_system_link.symlink_to(self.active_system_target)
        self.other_boot_link = self.directory / "other-boot-link"
        self.other_boot_link.symlink_to(self.other_boot_target)
        self.other_system_link = self.directory / "other-system-link"
        self.other_system_link.symlink_to(self.other_system_target)

        self.autoboot = self.directory / "autoboot.txt"
        self.autoboot.write_text("[all]\ntryboot_a_b=1\nboot_partition=2\n[tryboot]\nboot_partition=3\n")

        self.tools = self.directory / "tools"
        self.tools.mkdir()
        self.reboot_log = self.directory / "reboot.log"
        self.reboot = self.tools / "reboot"
        self.reboot.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> {self.reboot_log}\n")
        self.reboot.chmod(0o755)
        self.tryboot_helper = self.tools / "rpi-slot-tryboot"
        self.tryboot_helper.write_text(
            "#!/bin/sh\nprintf '[all]\\ntryboot_a_b=1\\nboot_partition=3\\n[tryboot]\\nboot_partition=2\\n'\n"
        )
        self.tryboot_helper.chmod(0o755)
        self.health = self.tools / "health"
        self.health.write_text("#!/bin/sh\nexit 0\n")
        self.health.chmod(0o755)

        self.boot_image = self.directory / "artifact-boot.img"
        self.boot_image.write_bytes(b"BOOT" * 256)
        self.root_image = self.directory / "artifact-root.img"
        self.root_image.write_bytes(b"ROOT" * 512)

        self.manifest = {
            "schema_version": 1,
            "release": {
                "id": "sovereign-os-base-0.1.0-proof.2",
                "version": "0.1.0-proof.2",
                "published_at": "2026-08-02T00:00:00Z",
                "channel": "preview",
                "notes_url": "https://example.invalid/notes",
            },
            "compatibility": {
                "devices": ["rpi5-arm64"],
                "source_versions": {"minimum": "0.1.0-proof.1", "maximum_exclusive": "0.2.0"},
                "allow_downgrade": False,
            },
            "artifacts": [
                {
                    "role": "system_boot",
                    "url": "https://example.invalid/boot.img",
                    "size": self.boot_image.stat().st_size,
                    "sha256": self._sha256(self.boot_image),
                    "media_type": "application/vnd.sovereign.base-os.boot.v1+raw",
                },
                {
                    "role": "system_root",
                    "url": "https://example.invalid/root.img",
                    "size": self.root_image.stat().st_size,
                    "sha256": self._sha256(self.root_image),
                    "media_type": "application/vnd.sovereign.base-os.root.v1+raw",
                },
            ],
            "components": {"image_base": {"version": "0.1.0-proof.2"}},
            "requirements": {"free_bytes": 1, "reboot": True},
            "rollback": {"supported": True, "requires_data_restore": False, "limitations": ["Must reflash to move to an older base-OS version."]},
            "signing": {"algorithm": "Ed25519", "key_id": "preview-test"},
        }
        self.manifest_path, self.signature_path = self._write_signed_manifest()

    @staticmethod
    def _sha256(path):
        import hashlib
        digest = hashlib.sha256()
        digest.update(Path(path).read_bytes())
        return digest.hexdigest()

    def _write_signed_manifest(self):
        manifest_path = self.directory / "base-os-manifest.json"
        signature_binary = self.directory / "signature.bin"
        signature_path = self.directory / "base-os-manifest.sig"
        manifest_path.write_text(json.dumps(self.manifest, separators=(",", ":")) + "\n")
        subprocess.run(
            [OPENSSL, "pkeyutl", "-sign", "-inkey", self.private_key, "-rawin", "-in", manifest_path, "-out", signature_binary],
            check=True, capture_output=True,
        )
        signature_path.write_text(base64.b64encode(signature_binary.read_bytes()).decode())
        return manifest_path, signature_path

    def environment(self):
        return os.environ | {
            "SOVEREIGN_UPDATE_POLICY": str(self.policy),
            "SOVEREIGN_RELEASE_PATH": str(self.release),
            "SOVEREIGN_BASE_OS_RELEASE_PATH": str(self.base_os_release),
            "SOVEREIGN_DATA_PATH": str(self.data_path),
            "SOVEREIGN_UPDATE_ROOT": str(self.directory / "update-state"),
            "SOVEREIGN_STATE_ROOT": str(self.state_root),
            "SOVEREIGN_OPENSSL": OPENSSL,
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
            "SOVEREIGN_SLOT_OTHER_BOOT_DEVICE": str(self.other_boot_link),
            "SOVEREIGN_SLOT_OTHER_SYSTEM_DEVICE": str(self.other_system_link),
            "SOVEREIGN_SLOT_ACTIVE_BOOT_DEVICE": str(self.active_boot_link),
            "SOVEREIGN_SLOT_ACTIVE_SYSTEM_DEVICE": str(self.active_system_link),
            "SOVEREIGN_AUTOBOOT_PATH": str(self.autoboot),
            "SOVEREIGN_RPI_SLOT_TRYBOOT": str(self.tryboot_helper),
            "SOVEREIGN_REBOOT": str(self.reboot),
            "SOVEREIGN_UPDATE_HEALTH_CHECK": str(self.health),
        }

    def run_client(self, *args):
        return subprocess.run(
            [str(CLIENT), *args], env=self.environment(), capture_output=True, text=True,
        )

    def stage(self):
        result = self.run_client(
            "stage-base-os",
            "--manifest", str(self.manifest_path),
            "--signature", str(self.signature_path),
            "--boot", str(self.boot_image),
            "--root", str(self.root_image),
        )
        self.assertEqual(0, result.returncode, result.stderr)
        return json.loads(result.stdout)["transaction_id"]

    def test_stage_writes_both_images_to_the_inactive_slot_only(self):
        self.stage()
        self.assertEqual(self.boot_image.read_bytes(), self.other_boot_target.read_bytes())
        self.assertEqual(self.root_image.read_bytes(), self.other_system_target.read_bytes())
        # The active slot's own files must be completely untouched.
        self.assertEqual(b"active boot\n", self.active_boot_target.read_bytes())
        self.assertEqual(b"active system\n", self.active_system_target.read_bytes())

    def test_full_success_path_reaches_committed_and_rewrites_autoboot(self):
        transaction_id = self.stage()

        trial = self.run_client("trial-base-os", transaction_id)
        self.assertEqual(0, trial.returncode, trial.stderr)
        self.assertEqual("0 tryboot", self.reboot_log.read_text().strip())

        verify = self.run_client("verify-base-os-trial")
        self.assertEqual(0, verify.returncode, verify.stderr)
        self.assertEqual("validated", json.loads(verify.stdout)["status"])

        commit = self.run_client("commit-base-os", transaction_id)
        self.assertEqual(0, commit.returncode, commit.stderr)
        self.assertEqual("committed", json.loads(commit.stdout)["status"])

        # The promoted config from the (stubbed) rpi-slot-tryboot helper
        # actually landed on the real autoboot.txt path, and a plain
        # (non-tryboot) reboot was triggered to boot into it.
        self.assertIn("boot_partition=3", self.autoboot.read_text())
        log_lines = self.reboot_log.read_text().splitlines()
        self.assertEqual(["0 tryboot", ""], log_lines)  # second reboot call passed no args

        status = self.run_client("status")
        self.assertEqual(0, status.returncode, status.stderr)
        payload = json.loads(status.stdout)
        self.assertEqual("committed", payload["base_os_update_state"])
        self.assertEqual("0.1.0-proof.2", payload["base_os_target_version"])

    def test_health_check_failure_reboots_without_committing(self):
        transaction_id = self.stage()
        self.run_client("trial-base-os", transaction_id)

        self.health.write_text("#!/bin/sh\necho boom >&2\nexit 1\n")
        self.health.chmod(0o755)

        verify = self.run_client("verify-base-os-trial")
        self.assertEqual(0, verify.returncode, verify.stderr)
        payload = json.loads(verify.stdout)
        self.assertEqual("trial_failed", payload["status"])

        # A plain reboot (no tryboot argument) was issued so the device
        # falls back to the untouched, already-committed original slot --
        # the same "just let the one-shot trial lapse" path a crash or
        # power loss takes for free, made explicit here instead of left
        # running on a demonstrably unhealthy trial slot.
        log_lines = self.reboot_log.read_text().splitlines()
        self.assertEqual(["0 tryboot", ""], log_lines)

        status = self.run_client("status")
        self.assertEqual(0, status.returncode, status.stderr)
        self.assertEqual("trial_failed", json.loads(status.stdout)["base_os_update_state"])

    def test_second_verify_call_with_no_trial_in_progress_is_a_no_op(self):
        result = self.run_client("verify-base-os-trial")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("no_trial_in_progress", json.loads(result.stdout)["status"])
        self.assertFalse(self.reboot_log.exists())

    def test_commit_before_validated_is_rejected(self):
        transaction_id = self.stage()
        result = self.run_client("commit-base-os", transaction_id)
        self.assertEqual(2, result.returncode)
        self.assertEqual("INVALID_TRANSACTION_STATE", json.loads(result.stderr)["code"])


if __name__ == "__main__":
    unittest.main()
