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
APPLIANCE = ROOT / "image-builder/sovereign/appliance"


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
            "SOVEREIGN_NGINX": str(self.nginx),
            "SOVEREIGN_UPDATE_TEST_MODE": "1",
            "SOVEREIGN_TEST_SERVICE_LOG": str(self.service_log),
        }

    def build_update_bundle(self, mutate=None):
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
        if mutate is not None:
            mutate(release)
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

    def stage_mutated_bundle(self, mutate):
        self.build_update_bundle(mutate)
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
        staged = subprocess.run(
            [str(CLIENT), "stage", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        return transaction_id, staged

    def test_stage_rejects_unknown_appliance_file(self):
        def add_unknown(release):
            (release / "appliance/console/unknown.js").write_text("fixture\n")

        transaction_id, staged = self.stage_mutated_bundle(add_unknown)
        self.assertEqual(2, staged.returncode)
        self.assertEqual("INCOMPLETE_RELEASE", json.loads(staged.stderr)["code"])
        self.assertFalse(
            self.releases.joinpath("releases/0.1.0-preview.6").exists()
        )
        self.assertFalse(
            self.directory.joinpath(
                "update-state/transactions", transaction_id, "release-candidate"
            ).exists()
        )

    def test_stage_rejects_invalid_appliance_script(self):
        def break_script(release):
            (release / "appliance/bin/stop-pihole").write_text(
                "#!/bin/sh\nif broken\n"
            )
            (release / "appliance/bin/stop-pihole").chmod(0o755)

        _, staged = self.stage_mutated_bundle(break_script)
        self.assertEqual(2, staged.returncode)
        self.assertEqual(
            "INVALID_APPLIANCE_SCRIPT", json.loads(staged.stderr)["code"]
        )

    def test_stage_rejects_incorrect_appliance_mode(self):
        def weaken_mode(release):
            (release / "appliance/bin/stop-pihole").chmod(0o644)

        _, staged = self.stage_mutated_bundle(weaken_mode)
        self.assertEqual(2, staged.returncode)
        self.assertEqual("UNSAFE_RELEASE_MODE", json.loads(staged.stderr)["code"])

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
        self.assertEqual(
            [
                "stop sovereign-pihole.service",
                "start sovereign-pihole.service",
                "stop sovereign-local-access.service",
                "stop nginx.service",
                "stop sovereign-console.service",
                "stop sovereign-pihole.service",
                "start sovereign-pihole.service",
                "start sovereign-console.service",
                "start nginx.service",
                "start sovereign-local-access.service",
            ],
            self.service_log.read_text().splitlines(),
        )

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

    def test_qualification_health_failure_rolls_back_with_real_health_check(self):
        transaction_id = self.prepare_and_backup_bundle()
        staged = subprocess.run(
            [str(CLIENT), "stage", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, staged.returncode, staged.stderr)
        environment = self.environment() | {
            "SOVEREIGN_UPDATE_QUALIFICATION": "1",
            "SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH": "1",
        }
        activated = subprocess.run(
            [str(CLIENT), "activate", transaction_id],
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, activated.returncode)
        self.assertEqual(
            "POSTUPDATE_HEALTH_FAILED", json.loads(activated.stderr)["code"]
        )
        self.assertEqual("0.1.0-preview.5", self.releases.joinpath("current").resolve().name)
        state = json.loads(
            (
                self.directory
                / "update-state/transactions"
                / transaction_id
                / "state.json"
            ).read_text()
        )
        self.assertEqual("rolled_back", state["state"])
        self.assertEqual(
            [
                "stop sovereign-pihole.service",
                "start sovereign-pihole.service",
                "stop sovereign-local-access.service",
                "stop nginx.service",
                "stop sovereign-console.service",
                "stop sovereign-pihole.service",
                "start sovereign-pihole.service",
                "start sovereign-console.service",
                "start nginx.service",
                "start sovereign-local-access.service",
                "stop sovereign-local-access.service",
                "stop nginx.service",
                "stop sovereign-console.service",
                "stop sovereign-pihole.service",
                "start sovereign-pihole.service",
                "start sovereign-console.service",
                "start nginx.service",
                "start sovereign-local-access.service",
            ],
            self.service_log.read_text().splitlines(),
        )

    def test_boot_recovery_restores_previous_release_pointer(self):
        transaction_id = self.prepare_and_backup_bundle()
        staged = subprocess.run(
            [str(CLIENT), "stage", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, staged.returncode, staged.stderr)
        transaction = self.directory / "update-state/transactions" / transaction_id
        state_path = transaction / "state.json"
        state = json.loads(state_path.read_text())
        state["state"] = "validating"
        state["sequence"] += 2
        state_path.write_text(json.dumps(state))
        (transaction / "activation.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "previous_release": "0.1.0-preview.5",
                    "target_release": "0.1.0-preview.6",
                }
            )
        )
        current = self.releases / "current"
        current.unlink()
        current.symlink_to("releases/0.1.0-preview.6")
        recovered = subprocess.run(
            [str(CLIENT), "recover"],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, recovered.returncode, recovered.stderr)
        self.assertEqual("0.1.0-preview.5", current.resolve().name)
        state = json.loads(state_path.read_text())
        self.assertEqual("recovery_required", state["state"])
        self.assertEqual("INTERRUPTED_TRANSACTION", state["failure"]["code"])

    def test_qualification_interrupt_requires_explicit_arming(self):
        manifest, signature = self.write_signed_manifest()
        environment = self.environment() | {
            "SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT": "backing_up"
        }
        prepared = subprocess.run(
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
        self.assertEqual(2, prepared.returncode)
        self.assertEqual(
            "QUALIFICATION_NOT_ARMED", json.loads(prepared.stderr)["code"]
        )

    def test_qualification_interrupt_at_backing_up_is_recoverable(self):
        manifest, signature = self.write_signed_manifest()
        prepared = self.run_prepare(manifest, signature)
        transaction_id = json.loads(prepared.stdout)["transaction_id"]
        environment = self.environment() | {
            "SOVEREIGN_UPDATE_QUALIFICATION": "1",
            "SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT": "backing_up",
        }
        interrupted = subprocess.run(
            [str(CLIENT), "backup", transaction_id],
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(75, interrupted.returncode)
        transaction = self.directory / "update-state/transactions" / transaction_id
        self.assertEqual(
            "backing_up", json.loads((transaction / "state.json").read_text())["state"]
        )
        self.assertFalse(self.service_log.exists())

        recovered = subprocess.run(
            [str(CLIENT), "recover"],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, recovered.returncode, recovered.stderr)
        state = json.loads((transaction / "state.json").read_text())
        self.assertEqual("recovery_required", state["state"])

    def run_interrupted_activation(self, boundary):
        transaction_id = self.prepare_and_backup_bundle()
        staged = subprocess.run(
            [str(CLIENT), "stage", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, staged.returncode, staged.stderr)
        environment = self.environment() | {
            "SOVEREIGN_UPDATE_QUALIFICATION": "1",
            "SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT": boundary,
        }
        interrupted = subprocess.run(
            [str(CLIENT), "activate", transaction_id],
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(75, interrupted.returncode)
        transaction = self.directory / "update-state/transactions" / transaction_id
        self.assertEqual(
            boundary, json.loads((transaction / "state.json").read_text())["state"]
        )
        return transaction_id, transaction

    def test_qualification_interrupt_at_activating_is_recoverable(self):
        transaction_id, transaction = self.run_interrupted_activation("activating")
        self.assertEqual("0.1.0-preview.5", self.releases.joinpath("current").resolve().name)

        recovered = subprocess.run(
            [str(CLIENT), "recover"],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, recovered.returncode, recovered.stderr)
        self.assertEqual("0.1.0-preview.5", self.releases.joinpath("current").resolve().name)
        self.assertEqual(
            "recovery_required",
            json.loads((transaction / "state.json").read_text())["state"],
        )

        discarded = subprocess.run(
            [str(CLIENT), "discard", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, discarded.returncode, discarded.stderr)
        self.assertFalse(self.releases.joinpath("releases/0.1.0-preview.6").exists())
        self.assertFalse(transaction.joinpath("release-candidate").exists())
        self.assertFalse(transaction.joinpath("staging/update-bundle.tar.zst").exists())
        self.assertTrue(transaction.joinpath("state.json").exists())
        self.assertTrue(transaction.joinpath("events.jsonl").exists())
        self.assertEqual(
            "discarded", json.loads((transaction / "state.json").read_text())["state"]
        )

    def test_qualification_interrupt_at_validating_restores_previous_pointer(self):
        transaction_id, transaction = self.run_interrupted_activation("validating")
        self.assertEqual("0.1.0-preview.6", self.releases.joinpath("current").resolve().name)

        recovered = subprocess.run(
            [str(CLIENT), "recover"],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, recovered.returncode, recovered.stderr)
        self.assertEqual("0.1.0-preview.5", self.releases.joinpath("current").resolve().name)
        state = json.loads((transaction / "state.json").read_text())
        self.assertEqual("recovery_required", state["state"])
        self.assertEqual("INTERRUPTED_TRANSACTION", state["failure"]["code"])

    def test_discard_refuses_active_target_release(self):
        transaction_id, transaction = self.run_interrupted_activation("validating")
        recovered_state = json.loads((transaction / "state.json").read_text())
        recovered_state["state"] = "recovery_required"
        (transaction / "state.json").write_text(json.dumps(recovered_state))
        discarded = subprocess.run(
            [str(CLIENT), "discard", transaction_id],
            env=self.environment(),
            capture_output=True,
            text=True,
        )
        self.assertEqual(2, discarded.returncode)
        self.assertEqual("DISCARD_TARGET_ACTIVE", json.loads(discarded.stderr)["code"])
        self.assertTrue(self.releases.joinpath("releases/0.1.0-preview.6").is_dir())


if __name__ == "__main__":
    unittest.main()
