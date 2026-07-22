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


@unittest.skipIf(OPENSSL is None, "OpenSSL is unavailable")
class UpdateClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.trust = self.directory / "trust"
        self.trust.mkdir()
        self.release = self.directory / "sovereign-release"
        self.release.write_text('NAME="Sovereign OS"\nVERSION="0.1.0-preview.5"\n')
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
        environment = os.environ | {
            "SOVEREIGN_UPDATE_POLICY": str(self.policy),
            "SOVEREIGN_RELEASE_PATH": str(self.release),
            "SOVEREIGN_DATA_PATH": str(self.directory),
            "SOVEREIGN_UPDATE_ROOT": str(self.directory / "update-state"),
            "SOVEREIGN_OPENSSL": OPENSSL,
        }
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


if __name__ == "__main__":
    unittest.main()
