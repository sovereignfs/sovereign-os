import base64
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
OPENSSL = shutil.which("openssl")


@unittest.skipIf(OPENSSL is None, "OpenSSL is unavailable")
class TrustRotationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.trust = self.directory / "trust"
        self.trust.mkdir()
        self.update_root = self.directory / "update-state"
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
        self.signer_id = "preview-2026-01"
        self.signer_private, self.signer_public = self.generate_keypair()
        self.install_trust_key(self.signer_id, self.signer_public, ["preview"], revoked=False)

    def tearDown(self):
        self.temporary.cleanup()

    def generate_keypair(self):
        private_path = self.directory / f"private-{os.urandom(4).hex()}.pem"
        public_path = self.directory / f"public-{os.urandom(4).hex()}.pem"
        subprocess.run(
            [OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", private_path],
            check=True, capture_output=True,
        )
        subprocess.run(
            [OPENSSL, "pkey", "-in", private_path, "-pubout", "-out", public_path],
            check=True, capture_output=True,
        )
        return private_path, public_path

    def install_trust_key(self, key_id, public_path, channels, revoked):
        shutil.copyfile(public_path, self.trust / f"{key_id}.pem")
        (self.trust / f"{key_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "key_id": key_id,
                    "algorithm": "Ed25519",
                    "channels": channels,
                    "revoked": revoked,
                }
            )
        )

    def environment(self):
        return os.environ | {
            "SOVEREIGN_UPDATE_POLICY": str(self.policy),
            "SOVEREIGN_UPDATE_ROOT": str(self.update_root),
            "SOVEREIGN_OPENSSL": OPENSSL,
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
        }

    def sign_manifest(self, manifest, private_key):
        manifest_path = self.directory / f"manifest-{os.urandom(4).hex()}.json"
        signature_path = manifest_path.with_suffix(".sig")
        signature_binary = manifest_path.with_suffix(".bin")
        manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n")
        subprocess.run(
            [
                OPENSSL, "pkeyutl", "-sign", "-inkey", private_key,
                "-rawin", "-in", manifest_path, "-out", signature_binary,
            ],
            check=True, capture_output=True,
        )
        signature_path.write_text(base64.b64encode(signature_binary.read_bytes()).decode())
        return manifest_path, signature_path

    def run_rotate(self, manifest, private_key):
        manifest_path, signature_path = self.sign_manifest(manifest, private_key)
        return subprocess.run(
            [str(CLIENT), "rotate-trust", "--manifest", str(manifest_path), "--signature", str(signature_path)],
            env=self.environment(), capture_output=True, text=True,
        )

    def add_operation(self, key_id, public_path, channels=("preview",)):
        return {
            "action": "add",
            "key_id": key_id,
            "algorithm": "Ed25519",
            "channels": list(channels),
            "public_key": public_path.read_text(),
        }

    def base_manifest(self, operations, channel="preview", signer=None):
        return {
            "schema_version": 1,
            "channel": channel,
            "published_at": "2026-07-30T00:00:00Z",
            "operations": operations,
            "signing": {"algorithm": "Ed25519", "key_id": signer or self.signer_id},
        }

    def test_rotate_trust_adds_new_key(self):
        _, new_public = self.generate_keypair()
        manifest = self.base_manifest([self.add_operation("preview-2026-02", new_public)])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual([{"action": "add", "key_id": "preview-2026-02"}], payload["operations"])
        metadata = json.loads((self.trust / "preview-2026-02.json").read_text())
        self.assertEqual(["preview"], metadata["channels"])
        self.assertFalse(metadata["revoked"])
        self.assertEqual(new_public.read_text(), (self.trust / "preview-2026-02.pem").read_text())

    def test_rotate_trust_revokes_a_different_key(self):
        _, other_public = self.generate_keypair()
        self.install_trust_key("preview-old", other_public, ["preview"], revoked=False)
        manifest = self.base_manifest([{"action": "revoke", "key_id": "preview-old"}])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(0, result.returncode, result.stderr)
        metadata = json.loads((self.trust / "preview-old.json").read_text())
        self.assertTrue(metadata["revoked"])

    def test_rotate_trust_allows_signer_to_retire_itself_with_replacement(self):
        _, new_public = self.generate_keypair()
        manifest = self.base_manifest([
            self.add_operation("preview-2026-02", new_public),
            {"action": "revoke", "key_id": self.signer_id},
        ])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads((self.trust / f"{self.signer_id}.json").read_text())["revoked"])
        self.assertFalse(json.loads((self.trust / "preview-2026-02.json").read_text())["revoked"])

    def test_rotate_trust_rejects_lockout_when_sole_key_self_revokes(self):
        manifest = self.base_manifest([{"action": "revoke", "key_id": self.signer_id}])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("TRUST_LOCKOUT_REJECTED", json.loads(result.stderr)["code"])
        self.assertFalse(json.loads((self.trust / f"{self.signer_id}.json").read_text())["revoked"])

    def test_rotate_trust_rejects_wrong_signature(self):
        other_private, _ = self.generate_keypair()
        _, new_public = self.generate_keypair()
        manifest = self.base_manifest([self.add_operation("preview-2026-02", new_public)])
        result = self.run_rotate(manifest, other_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("SIGNATURE_MISMATCH", json.loads(result.stderr)["code"])
        self.assertFalse((self.trust / "preview-2026-02.json").exists())

    def test_rotate_trust_rejects_revoked_signer(self):
        metadata = json.loads((self.trust / f"{self.signer_id}.json").read_text())
        metadata["revoked"] = True
        (self.trust / f"{self.signer_id}.json").write_text(json.dumps(metadata))
        _, new_public = self.generate_keypair()
        manifest = self.base_manifest([self.add_operation("preview-2026-02", new_public)])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("REVOKED_SIGNING_KEY", json.loads(result.stderr)["code"])

    def test_rotate_trust_rejects_channel_mismatch_with_policy(self):
        _, new_public = self.generate_keypair()
        self.install_trust_key("stable-signer", new_public, ["stable"], revoked=False)
        stable_private, stable_public = self.generate_keypair()
        self.install_trust_key("stable-signer-2", stable_public, ["stable"], revoked=False)
        _, another_public = self.generate_keypair()
        manifest = self.base_manifest(
            [self.add_operation("stable-2026-01", another_public, channels=["stable"])],
            channel="stable",
            signer="stable-signer-2",
        )
        result = self.run_rotate(manifest, stable_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("WRONG_CHANNEL", json.loads(result.stderr)["code"])

    def test_rotate_trust_rejects_replacing_existing_key_id(self):
        _, new_public = self.generate_keypair()
        manifest = self.base_manifest([self.add_operation(self.signer_id, new_public)])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("TRUST_KEY_EXISTS", json.loads(result.stderr)["code"])

    def test_rotate_trust_rejects_revoking_unknown_key(self):
        manifest = self.base_manifest([{"action": "revoke", "key_id": "does-not-exist"}])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("REVOKE_UNKNOWN_KEY", json.loads(result.stderr)["code"])

    def test_rotate_trust_rejects_invalid_public_key_material(self):
        manifest = self.base_manifest([
            {
                "action": "add",
                "key_id": "preview-broken",
                "algorithm": "Ed25519",
                "channels": ["preview"],
                "public_key": "not a real key\n",
            }
        ])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(2, result.returncode)
        self.assertEqual("INVALID_TRUST_KEY", json.loads(result.stderr)["code"])
        self.assertFalse((self.trust / "preview-broken.pem").exists())

    def test_rotate_trust_records_audit_log(self):
        _, new_public = self.generate_keypair()
        manifest = self.base_manifest([self.add_operation("preview-2026-02", new_public)])
        result = self.run_rotate(manifest, self.signer_private)
        self.assertEqual(0, result.returncode, result.stderr)
        log_lines = (self.update_root / "trust-rotations.jsonl").read_text().splitlines()
        self.assertEqual(1, len(log_lines))
        entry = json.loads(log_lines[0])
        self.assertEqual(self.signer_id, entry["signed_by"])
        self.assertEqual([{"action": "add", "key_id": "preview-2026-02"}], entry["operations"])


if __name__ == "__main__":
    unittest.main()
