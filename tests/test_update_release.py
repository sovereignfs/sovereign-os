import base64
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
            llama_env = temporary / "llama-image.env"
            llama_env.write_text(
                "LLAMA_IMAGE_REPOSITORY='ghcr.io/ggml-org/llama.cpp'\n"
                "LLAMA_IMAGE_TAG='server'\n"
                f"LLAMA_IMAGE_DIGEST='sha256:{'b' * 64}'\n"
                "LLAMA_IMAGE_PLATFORM='linux/arm64'\n"
            )
            llama_oci = temporary / "llama.oci.tar"
            llama_oci.write_bytes(b"llama OCI fixture\n")
            searxng_env = temporary / "searxng-image.env"
            searxng_env.write_text(
                "SEARXNG_IMAGE_REPOSITORY='ghcr.io/searxng/searxng'\n"
                "SEARXNG_IMAGE_TAG='latest'\n"
                f"SEARXNG_IMAGE_DIGEST='sha256:{'c' * 64}'\n"
                "SEARXNG_IMAGE_PLATFORM='linux/arm64'\n"
            )
            searxng_oci = temporary / "searxng.oci.tar"
            searxng_oci.write_bytes(b"searxng OCI fixture\n")
            output = temporary / "release"
            subprocess.run(
                [
                    str(CREATE), "--version", "0.1.0-preview.7",
                    "--source-minimum", "0.1.0-preview.6",
                    "--source-maximum-exclusive", "0.2.0",
                    "--pihole-env", str(pihole), "--oci", str(oci),
                    "--llama-env", str(llama_env), "--llama-oci", str(llama_oci),
                    "--searxng-env", str(searxng_env), "--searxng-oci", str(searxng_oci),
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
            self.assertEqual(
                f"sha256:{'b' * 64}", manifest["components"]["llama"]["digest"]
            )
            self.assertEqual(
                f"sha256:{'c' * 64}", manifest["components"]["searxng"]["digest"]
            )
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
                self.assertIn(
                    "sovereign-update-v1/release/appliance/bin/start-llama-server",
                    names,
                )
                self.assertIn(
                    "sovereign-update-v1/release/llama-image.env",
                    names,
                )
                self.assertIn(
                    "sovereign-update-v1/release/llama-arm64.oci.tar",
                    names,
                )
                self.assertIn(
                    "sovereign-update-v1/release/searxng-image.env",
                    names,
                )
                self.assertIn(
                    "sovereign-update-v1/release/searxng-arm64.oci.tar",
                    names,
                )
                self.assertIn(
                    "sovereign-update-v1/release/appliance/bin/start-searxng",
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
                    0o755,
                    modes["release/appliance/bin/start-llama-server"],
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

    def test_ignores_stray_pycache_in_appliance_source(self):
        # appliance/lib/*.py are real importable modules (unlike the rest
        # of appliance/, which is extension-less scripts) -- running tests
        # locally generates __pycache__ there as a side effect. A release
        # build must not choke on that bytecode cache.
        appliance = ROOT / "image-builder/sovereign/appliance"
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            copied_appliance = temporary / "appliance"
            shutil.copytree(appliance, copied_appliance)
            pycache = copied_appliance / "lib" / "__pycache__"
            pycache.mkdir(parents=True, exist_ok=True)
            (pycache / "sovereign_capabilities.cpython-314.pyc").write_bytes(b"not real bytecode")

            pihole = temporary / "pihole-image.env"
            pihole.write_text(
                "PIHOLE_IMAGE_REPOSITORY='docker.io/pihole/pihole'\n"
                "PIHOLE_IMAGE_TAG='fixture'\n"
                f"PIHOLE_IMAGE_DIGEST='sha256:{'a' * 64}'\n"
                "PIHOLE_IMAGE_PLATFORM='linux/arm64'\n"
            )
            oci = temporary / "pihole.oci.tar"
            oci.write_bytes(b"OCI fixture\n")
            llama_env = temporary / "llama-image.env"
            llama_env.write_text(
                "LLAMA_IMAGE_REPOSITORY='ghcr.io/ggml-org/llama.cpp'\n"
                "LLAMA_IMAGE_TAG='server'\n"
                f"LLAMA_IMAGE_DIGEST='sha256:{'b' * 64}'\n"
                "LLAMA_IMAGE_PLATFORM='linux/arm64'\n"
            )
            llama_oci = temporary / "llama.oci.tar"
            llama_oci.write_bytes(b"llama OCI fixture\n")
            searxng_env = temporary / "searxng-image.env"
            searxng_env.write_text(
                "SEARXNG_IMAGE_REPOSITORY='ghcr.io/searxng/searxng'\n"
                "SEARXNG_IMAGE_TAG='latest'\n"
                f"SEARXNG_IMAGE_DIGEST='sha256:{'c' * 64}'\n"
                "SEARXNG_IMAGE_PLATFORM='linux/arm64'\n"
            )
            searxng_oci = temporary / "searxng.oci.tar"
            searxng_oci.write_bytes(b"searxng OCI fixture\n")
            output = temporary / "release"
            subprocess.run(
                [
                    str(CREATE), "--version", "0.1.0-preview.7",
                    "--source-minimum", "0.1.0-preview.6",
                    "--source-maximum-exclusive", "0.2.0",
                    "--pihole-env", str(pihole), "--oci", str(oci),
                    "--llama-env", str(llama_env), "--llama-oci", str(llama_oci),
                    "--searxng-env", str(searxng_env), "--searxng-oci", str(searxng_oci),
                    "--appliance-dir", str(copied_appliance),
                    "--output-dir", str(output), "--key-id", "preview-test",
                    "--artifact-base-url", "https://example.invalid/release",
                    "--notes-url", "https://example.invalid/notes",
                    "--source-date-epoch", "1700000000", "--zstd", ZSTD,
                ],
                check=True,
                capture_output=True,
            )
            self.assertTrue((output / "release-manifest.json").is_file())

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
        wants = next(line for line in pihole.splitlines() if line.startswith("Wants="))
        self.assertNotIn("sovereign-update-recovery.service", wants)
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

    def test_trims_dtbs_for_boards_this_product_does_not_support(self):
        # This image targets Raspberry Pi 5 only, but the upstream
        # firmware/kernel packages ship device trees for the whole
        # Raspberry Pi family. Confirmed present and unused on real
        # hardware during RFC-0016 research
        # (docs/rfcs/0016-full-base-os-updates.md): 11 bcm2710/bcm2711
        # files (Pi 2/3/CM0/CM3/Zero 2, Pi 4/400/CM4) alongside the 9
        # bcm2712 files this product actually needs.
        hook = (
            ROOT
            / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize91-trim-dtbs"
        )
        self.assertTrue(hook.is_file())
        mode = hook.stat().st_mode
        self.assertTrue(mode & stat.S_IXUSR, "hook must be executable")

        result = subprocess.run(["sh", "-n", str(hook)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

        content = hook.read_text()
        rm_block = content[content.index("rm -f") :]
        self.assertIn("bcm2710-", rm_block)
        self.assertIn("bcm2711-", rm_block)
        self.assertNotIn("bcm2712", rm_block)

    def test_prune_timer_is_enabled_and_hardened(self):
        overlay = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
        service = (overlay / "etc/systemd/system/sovereign-update-prune.service").read_text()
        timer = (overlay / "etc/systemd/system/sovereign-update-prune.timer").read_text()
        enablement = (
            ROOT
            / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
        ).read_text()
        self.assertIn("ExecStart=/usr/sbin/sovereign-update prune", service)
        self.assertIn("ConditionPathIsMountPoint=/data", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectHome=yes", service)
        self.assertNotIn("[Install]", service)
        self.assertIn("OnCalendar=", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("WantedBy=timers.target", timer)
        self.assertIn("sovereign-update-prune.timer", enablement)
        self.assertNotIn("sovereign-update-prune.service", enablement)

    def test_check_timer_is_enabled_and_hardened(self):
        overlay = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
        service = (overlay / "etc/systemd/system/sovereign-update-check.service").read_text()
        timer = (overlay / "etc/systemd/system/sovereign-update-check.timer").read_text()
        enablement = (
            ROOT
            / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
        ).read_text()
        self.assertIn("ExecStart=/usr/sbin/sovereign-update check", service)
        self.assertIn("ConditionPathIsMountPoint=/data", service)
        self.assertIn("Wants=network-online.target", service)
        self.assertIn("NoNewPrivileges=yes", service)
        self.assertIn("ProtectHome=yes", service)
        self.assertNotIn("[Install]", service)
        self.assertIn("OnCalendar=", timer)
        self.assertIn("Persistent=true", timer)
        self.assertIn("WantedBy=timers.target", timer)
        self.assertIn("sovereign-update-check.timer", enablement)
        self.assertNotIn("sovereign-update-check.service", enablement)

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

    def test_workflow_builds_and_packages_base_os_candidate_before_upload(self):
        workflow = (ROOT / ".github/workflows/build-image.yml").read_text()

        # A base-OS candidate needs its own A/B-layout image build (the
        # primary "Build image" step above targets the plain, non-A/B
        # config and can never produce it) -- build, then package, then
        # upload, same shape as the appliance update candidate.
        build_base_os = workflow.index("Build base-OS image")
        package_base_os = workflow.index("Package unsigned base-OS update candidate")
        upload_base_os = workflow.index("Upload base-OS update artifact")
        self.assertLess(build_base_os, package_base_os)
        self.assertLess(package_base_os, upload_base_os)

        self.assertIn("SOVEREIGN_IMAGE_CONFIG: sovereign-ab-proof.yaml", workflow)
        self.assertIn("build/base-os-release/", workflow)
        self.assertIn(
            "name: sovereign-base-os-${{ inputs.version }}-rpi5-arm64",
            workflow,
        )

        image_upload = workflow.index("Upload image release artifact")
        self.assertLess(image_upload, upload_base_os)
        self.assertNotIn(
            "build/base-os-release/",
            workflow[image_upload:upload_base_os],
        )

        # The primary build never sets SOVEREIGN_IMAGE_CONFIG -- only the
        # dedicated base-OS build step does.
        primary_build = workflow.index("Build image")
        self.assertNotIn(
            "SOVEREIGN_IMAGE_CONFIG",
            workflow[primary_build:build_base_os],
        )

    def test_workflow_uploads_the_flashable_ab_image_gated_on_base_os_candidate(self):
        workflow = (ROOT / ".github/workflows/build-image.yml").read_text()

        # ADR-0011's external-recovery-image-path qualification needs the
        # actual flashable A/B disk image, not just the boot/root
        # partition images create-base-os-release.py extracts for the
        # base-OS update candidate. It has no release-bundle packaging of
        # its own -- create-release-bundle.py hardcodes plain-image
        # assumptions that don't hold for the A/B config's differently
        # named output -- so it's uploaded raw.
        upload_ab_image = workflow.index("Upload flashable A/B image artifact")
        build_base_os = workflow.index("Build base-OS image")
        self.assertLess(build_base_os, upload_ab_image)
        self.assertIn(
            "name: sovereign-os-ab-${{ inputs.version }}-rpi5-arm64",
            workflow,
        )
        self.assertIn(
            "build/sovereign-image-sovereign-ab-proof/deploy/*.img.zst",
            workflow,
        )
        # Gated the same way as every other base-OS-candidate step -- an
        # ordinary plain-image build must never try to upload this.
        section_start = workflow.index("Upload flashable A/B image artifact") - 200
        self.assertIn("if: inputs.build_base_os_candidate", workflow[section_start:upload_ab_image + 200])


if __name__ == "__main__":
    unittest.main()
