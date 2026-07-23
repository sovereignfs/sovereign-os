import base64
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CREATE = ROOT / "scripts/create-update-release.py"
SIGN = ROOT / "scripts/sign-update-manifest.py"
OPENSSL = shutil.which("openssl")
ZSTD = shutil.which("zstd")


@unittest.skipIf(OPENSSL is None or ZSTD is None, "OpenSSL or zstd unavailable")
class UpdateReleaseTests(unittest.TestCase):
    def test_creates_and_signs_installable_release_inputs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            pihole = temporary / "pihole-image.env"
            pihole.write_text(
                "PIHOLE_IMAGE_REPOSITORY='docker.io/pihole/pihole'\n"
                "PIHOLE_IMAGE_TAG='fixture'\n"
                f"PIHOLE_IMAGE_DIGEST='sha256:{'a' * 64}'\n"
                "PIHOLE_IMAGE_PLATFORM='linux/arm64'\n"
            )
            oci = temporary / "pihole.oci.tar"
            oci.write_bytes(b"OCI fixture\n")
            output = temporary / "release"
            subprocess.run(
                [
                    str(CREATE), "--version", "0.1.0-preview.7",
                    "--source-minimum", "0.1.0-preview.6",
                    "--source-maximum-exclusive", "0.2.0",
                    "--pihole-env", str(pihole), "--oci", str(oci),
                    "--output-dir", str(output), "--key-id", "preview-test",
                    "--artifact-base-url", "https://example.invalid/release",
                    "--notes-url", "https://example.invalid/notes",
                    "--source-date-epoch", "1700000000", "--zstd", ZSTD,
                ],
                check=True,
                capture_output=True,
            )
            manifest = json.loads((output / "release-manifest.json").read_text())
            self.assertEqual("0.1.0-preview.7", manifest["release"]["version"])
            bundle = output / "sovereign-update-0.1.0-preview.7-rpi5-arm64.tar.zst"
            self.assertEqual(bundle.stat().st_size, manifest["artifacts"][0]["size"])
            tar_path = temporary / "update.tar"
            subprocess.run([ZSTD, "-q", "-d", "-o", tar_path, bundle], check=True)
            with tarfile.open(tar_path) as archive:
                names = archive.getnames()
                self.assertIn(
                    "sovereign-update-v1/release/appliance/console/index.html",
                    names,
                )
                self.assertIn(
                    "sovereign-update-v1/release/appliance/bin/start-pihole",
                    names,
                )
                bundle_manifest = json.load(
                    archive.extractfile(
                        "sovereign-update-v1/bundle-manifest.json"
                    )
                )
                modes = {
                    entry["path"]: entry["mode"]
                    for entry in bundle_manifest["files"]
                }
                self.assertEqual(
                    0o755,
                    modes["release/appliance/bin/start-pihole"],
                )
                self.assertEqual(
                    0o644,
                    modes["release/appliance/console/index.html"],
                )
                console = archive.extractfile(
                    "sovereign-update-v1/release/appliance/console/index.html"
                ).read().decode()
                self.assertIn("Release 0.1.0-preview.7", console)
                self.assertNotIn("@SOVEREIGN_RELEASE_VERSION@", console)
            private = temporary / "private.pem"
            public = temporary / "public.pem"
            subprocess.run([OPENSSL, "genpkey", "-algorithm", "Ed25519", "-out", private], check=True)
            subprocess.run([OPENSSL, "pkey", "-in", private, "-pubout", "-out", public], check=True)
            signature = output / "release-manifest.sig"
            subprocess.run(
                [str(SIGN), "--manifest", str(output / "release-manifest.json"), "--private-key", str(private), "--output", str(signature), "--openssl", OPENSSL],
                check=True,
            )
            raw = temporary / "signature.bin"
            raw.write_bytes(base64.b64decode(signature.read_text()))
            verified = subprocess.run(
                [OPENSSL, "pkeyutl", "-verify", "-pubin", "-inkey", public, "-rawin", "-in", output / "release-manifest.json", "-sigfile", raw],
                capture_output=True,
            )
            self.assertEqual(0, verified.returncode)

    def test_image_enables_recovery_before_pihole(self):
        overlay = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
        recovery = (overlay / "etc/systemd/system/sovereign-update-recovery.service").read_text()
        pihole = (overlay / "etc/systemd/system/sovereign-pihole.service").read_text()
        enablement = (
            ROOT
            / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
        ).read_text()
        self.assertIn("Before=sovereign-pihole.service", recovery)
        self.assertIn("After=", pihole)
        self.assertIn("sovereign-update-recovery.service", pihole)
        self.assertIn(
            "ExecStop=/opt/sovereign/current/appliance/bin/stop-pihole",
            pihole,
        )
        self.assertIn(
            "docker compose",
            (ROOT / "image-builder/sovereign/appliance/bin/stop-pihole").read_text(),
        )
        self.assertIn("sovereign-update-recovery.service", enablement)
        wrapper = overlay / "usr/bin/sovereign-update"
        self.assertTrue(wrapper.is_file())
        self.assertIn("/usr/sbin/sovereign-update", wrapper.read_text())

    def test_workflow_packages_update_before_upload(self):
        workflow = (ROOT / ".github/workflows/build-image.yml").read_text()
        self.assertLess(
            workflow.index("Package unsigned appliance update candidate"),
            workflow.index("Upload installed-device update artifact"),
        )
        self.assertIn("build/update-release/", workflow)
        self.assertIn(
            "name: sovereign-update-${{ inputs.version }}-rpi5-arm64",
            workflow,
        )
        image_upload = workflow.index("Upload image release artifact")
        update_upload = workflow.index("Upload installed-device update artifact")
        self.assertLess(image_upload, update_upload)
        self.assertNotIn(
            "build/update-release/",
            workflow[image_upload:update_upload],
        )


if __name__ == "__main__":
    unittest.main()
