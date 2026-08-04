import base64
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CREATE = ROOT / "scripts/create-base-os-release.py"
SIGN = ROOT / "scripts/sign-update-manifest.py"
CLIENT = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update"
)
OPENSSL = shutil.which("openssl")
ZSTD = shutil.which("zstd")

SPEC = importlib.util.spec_from_loader("sovereign_update", SourceFileLoader("sovereign_update", str(CLIENT)))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@unittest.skipIf(OPENSSL is None or ZSTD is None, "OpenSSL or zstd unavailable")
class CreateBaseOsReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

        # Stand in for genimage's own raw (not android-sparse) boot.vfat /
        # root.ext4 intermediate outputs -- this script's job starts once
        # those already exist, the same relationship create-update-release.py
        # has to a pre-built Pi-hole OCI archive it doesn't build itself.
        self.boot = self.directory / "boot.vfat"
        self.boot.write_bytes(b"BOOT-PARTITION-FIXTURE" * 1000)
        self.root = self.directory / "root.ext4"
        self.root.write_bytes(b"ROOT-PARTITION-FIXTURE" * 5000)

        self.output = self.directory / "release"

    def run_create(self, **overrides):
        args = {
            "--version": "0.1.0-preview.2",
            "--source-minimum": "0.1.0-preview.1",
            "--source-maximum-exclusive": "0.2.0",
            "--boot": str(self.boot),
            "--root": str(self.root),
            "--output-dir": str(self.output),
            "--key-id": "preview-test",
            "--artifact-base-url": "https://example.invalid/release",
            "--notes-url": "https://example.invalid/notes",
            "--source-date-epoch": "1700000000",
            "--zstd": ZSTD,
        }
        args.update(overrides)
        command = [str(CREATE)]
        for key, value in args.items():
            command.extend([key, value])
        return subprocess.run(command, capture_output=True, text=True)

    def test_creates_a_manifest_that_validates_against_sovereign_update(self):
        result = self.run_create()
        self.assertEqual(0, result.returncode, result.stderr)

        manifest = json.loads((self.output / "base-os-manifest.json").read_text())
        self.assertEqual("0.1.0-preview.2", manifest["release"]["version"])
        self.assertEqual("0.1.0-preview.2", manifest["components"]["image_base"]["version"])
        self.assertTrue(manifest["requirements"]["reboot"])

        # The manifest this script produces must actually be accepted by
        # the exact validator stage-base-os itself runs -- the real
        # integration point, not just "this script's own idea of the
        # schema".
        by_role = MODULE.validate_base_os_manifest(manifest)
        self.assertEqual({"system_boot", "system_root"}, set(by_role))

    def test_artifacts_are_zstd_compressed_and_digests_match(self):
        result = self.run_create()
        self.assertEqual(0, result.returncode, result.stderr)
        manifest = json.loads((self.output / "base-os-manifest.json").read_text())
        by_role = {artifact["role"]: artifact for artifact in manifest["artifacts"]}

        boot_artifact = self.output / "sovereign-base-os-0.1.0-preview.2-rpi5-arm64-boot.img.zst"
        root_artifact = self.output / "sovereign-base-os-0.1.0-preview.2-rpi5-arm64-root.img.zst"
        self.assertTrue(boot_artifact.is_file())
        self.assertTrue(root_artifact.is_file())
        self.assertEqual(boot_artifact.stat().st_size, by_role["system_boot"]["size"])
        self.assertEqual(root_artifact.stat().st_size, by_role["system_root"]["size"])

        # Round-trips through the exact decompress-while-writing path
        # write_raw_artifact uses on a real device, onto a plain file
        # standing in for the block device.
        decompressed = self.directory / "decompressed-boot.img"
        with decompressed.open("wb") as destination:
            subprocess.run(
                [ZSTD, "--decompress", "--quiet", "--stdout", str(boot_artifact)],
                stdout=destination,
                check=True,
            )
        self.assertEqual(self.boot.read_bytes(), decompressed.read_bytes())

    def test_signed_manifest_verifies(self):
        result = self.run_create()
        self.assertEqual(0, result.returncode, result.stderr)

        private = self.directory / "private.pem"
        public = self.directory / "public.pem"
        subprocess.run([OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", private], check=True)
        subprocess.run([OPENSSL, "pkey", "-in", private, "-pubout", "-out", public], check=True)
        signature = self.output / "base-os-manifest.sig"
        subprocess.run(
            [
                str(SIGN), "--manifest", str(self.output / "base-os-manifest.json"),
                "--private-key", str(private), "--output", str(signature), "--openssl", OPENSSL,
            ],
            check=True,
        )
        raw = self.directory / "signature.bin"
        raw.write_bytes(base64.b64decode(signature.read_text()))
        verified = subprocess.run(
            [
                OPENSSL, "pkeyutl", "-verify", "-pubin", "-inkey", public, "-rawin",
                "-in", self.output / "base-os-manifest.json", "-sigfile", raw,
            ],
            capture_output=True,
        )
        self.assertEqual(0, verified.returncode)

    def test_rejects_a_non_empty_output_directory(self):
        self.output.mkdir()
        (self.output / "stray-file").write_text("x")
        result = self.run_create()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("not empty", result.stderr)

    def test_rejects_downgrade_disallowed_by_construction(self):
        result = self.run_create()
        self.assertEqual(0, result.returncode, result.stderr)
        manifest = json.loads((self.output / "base-os-manifest.json").read_text())
        self.assertFalse(manifest["compatibility"]["allow_downgrade"])

    def test_rejects_non_https_urls(self):
        result = self.run_create(**{"--artifact-base-url": "http://example.invalid/release"})
        self.assertNotEqual(0, result.returncode)
        self.assertIn("HTTPS", result.stderr)


if __name__ == "__main__":
    unittest.main()
