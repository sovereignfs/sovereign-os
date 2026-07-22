import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "scripts/prepare-update-qualification.py"
OPENSSL = shutil.which("openssl")


@unittest.skipIf(OPENSSL is None, "OpenSSL is unavailable")
class PrepareUpdateQualificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.update = self.directory / "update-release"
        self.update.mkdir()
        self.bundle = self.update / "sovereign-update-0.1.0-preview.8-rpi5-arm64.tar.zst"
        self.bundle.write_bytes(b"qualification bundle fixture\n")
        self.manifest = self.update / "release-manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "release": {
                        "version": "0.1.0-preview.8",
                        "channel": "preview",
                    },
                    "compatibility": {
                        "devices": ["rpi5-arm64"],
                        "source_versions": {
                            "minimum": "0.1.0-preview.7",
                            "maximum_exclusive": "0.2.0",
                        },
                    },
                    "artifacts": [
                        {
                            "role": "update_bundle",
                            "url": f"https://example.invalid/{self.bundle.name}",
                            "size": self.bundle.stat().st_size,
                            "sha256": hashlib.sha256(self.bundle.read_bytes()).hexdigest(),
                        }
                    ],
                    "signing": {"algorithm": "Ed25519", "key_id": "preview-local"},
                },
                separators=(",", ":"),
            )
            + "\n"
        )
        self.private_key = self.directory / "private.pem"
        subprocess.run(
            [OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", self.private_key],
            check=True,
            capture_output=True,
        )
        self.private_key.chmod(0o600)
        self.output = self.directory / "qualification-kit"

    def tearDown(self):
        self.temporary.cleanup()

    def run_prepare(self):
        return subprocess.run(
            [
                str(PREPARE),
                "--update-dir",
                str(self.update),
                "--private-key",
                str(self.private_key),
                "--output-dir",
                str(self.output),
                "--key-id",
                "preview-local",
                "--openssl",
                OPENSSL,
            ],
            capture_output=True,
            text=True,
        )

    def test_prepares_verified_kit_without_private_key(self):
        completed = self.run_prepare()
        self.assertEqual(0, completed.returncode, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual("prepared", result["status"])
        self.assertEqual("0.1.0-preview.7", result["source_minimum"])
        self.assertEqual("0.1.0-preview.8", result["target_version"])
        self.assertTrue(self.output.joinpath("release-manifest.sig").is_file())
        self.assertTrue(self.output.joinpath("preview-local.pem").is_file())
        self.assertTrue(self.output.joinpath("preview-local.json").is_file())
        self.assertFalse(any("private" in path.name for path in self.output.iterdir()))
        subprocess.run(
            ["sha256sum", "--check", "SHA256SUMS"],
            cwd=self.output,
            check=True,
            capture_output=True,
        )
        kit = json.loads(self.output.joinpath("qualification-kit.json").read_text())
        self.assertFalse(kit["private_key_included"])

    def test_rejects_permissive_private_key(self):
        self.private_key.chmod(0o644)
        completed = self.run_prepare()
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("private key must not be accessible", completed.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_artifact_digest_mismatch(self):
        self.bundle.write_bytes(b"tampered fixture\n")
        completed = self.run_prepare()
        self.assertNotEqual(0, completed.returncode)
        self.assertIn("does not match", completed.stderr)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
