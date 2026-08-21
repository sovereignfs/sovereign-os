import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
APPLIANCE = ROOT / "image-builder/sovereign/appliance"
SOVEREIGN_DIR = ROOT / "image-builder/sovereign"
ENABLE_UNITS = (
    ROOT
    / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
)

VERIFY_ARTIFACT = OVERLAY / "usr/lib/sovereign/verify-searxng-artifact"
IMPORT_IMAGE = OVERLAY / "usr/lib/sovereign/import-searxng-image"
START_SEARXNG = APPLIANCE / "bin/start-searxng"
STOP_SEARXNG = APPLIANCE / "bin/stop-searxng"
COMPOSE_TEMPLATE = APPLIANCE / "searxng/compose.yaml.in"
SETTINGS_FILE = APPLIANCE / "searxng/settings.yml"
SEARXNG_IMAGE_ENV = SOVEREIGN_DIR / "searxng-image.env"
ARTIFACT_SERVICE = OVERLAY / "etc/systemd/system/sovereign-searxng-artifact.service"
IMPORT_SERVICE = OVERLAY / "etc/systemd/system/sovereign-searxng-import.service"
SEARXNG_SERVICE = OVERLAY / "etc/systemd/system/sovereign-searxng.service"
IMAGER_PROVISION_SERVICE = OVERLAY / "etc/systemd/system/sovereign-imager-provision.service"
UPDATE_RECOVERY_SERVICE = OVERLAY / "etc/systemd/system/sovereign-update-recovery.service"
POST_BUILD = SOVEREIGN_DIR / "post-build.sh"


class SearxngImageEnvTests(unittest.TestCase):
    def test_pins_a_complete_digest_for_the_selected_image(self):
        content = SEARXNG_IMAGE_ENV.read_text()
        self.assertIn("SEARXNG_IMAGE_REPOSITORY='ghcr.io/searxng/searxng'", content)
        self.assertIn("SEARXNG_IMAGE_TAG='latest'", content)
        match = re.search(r"SEARXNG_IMAGE_DIGEST='sha256:([0-9a-f]+)'", content)
        self.assertIsNotNone(match)
        self.assertEqual(64, len(match.group(1)))
        self.assertIn("SEARXNG_IMAGE_PLATFORM='linux/arm64'", content)


class SettingsFileTests(unittest.TestCase):
    def test_overrides_exactly_the_defaults_rfc_0017_names(self):
        content = SETTINGS_FILE.read_text()
        self.assertIn("use_default_settings: true", content)
        # web.search needs JSON, not an HTML page to scrape -- disabled
        # upstream by default.
        self.assertIn("formats:", content)
        self.assertIn("- html", content)
        self.assertIn("- json", content)
        # Autocomplete is a second, undisclosed channel to an external
        # engine that fires on partial keystrokes -- must be off.
        self.assertIn('autocomplete: ""', content)
        # RFC-0017's explicit decisions, not left to inherited defaults.
        self.assertIn("limiter: false", content)
        self.assertIn("image_proxy: false", content)
        # The real per-device secret is never written into this file --
        # confirmed against the real image's settings_defaults.py, which
        # reads SEARXNG_SECRET from the environment unconditionally.
        self.assertNotIn("secret_key", content)


class VerifyArtifactScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(VERIFY_ARTIFACT)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_verifies_checksum_and_archive_contents_before_marking_ready(self):
        content = VERIFY_ARTIFACT.read_text()
        self.assertIn(". /usr/lib/sovereign/searxng-image.env", content)
        self.assertIn('sha256sum -c "${archive}.sha256"', content)
        self.assertIn('tar -tf "$archive" | grep -Fx "oci-layout"', content)
        self.assertIn('tar -tf "$archive" | grep -Fx "index.json"', content)
        self.assertIn("blobs/sha256/${manifest_digest}", content)
        self.assertIn("/data/sovereign/searxng-artifact-ready", content)


class ImportImageScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(IMPORT_IMAGE)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_loads_tags_and_verifies_platform_before_marking_ready(self):
        content = IMPORT_IMAGE.read_text()
        self.assertIn(". /usr/lib/sovereign/searxng-image.env", content)
        self.assertIn("docker load --input", content)
        self.assertIn('docker image tag "$SEARXNG_IMAGE_DIGEST" "$image"', content)
        self.assertIn('test "$platform" = "$SEARXNG_IMAGE_PLATFORM"', content)
        self.assertIn("marker=${state_dir}/searxng-import-ready", content)
        self.assertIn('mv "${marker}.tmp" "$marker"', content)

    def test_is_idempotent_when_already_imported(self):
        # Mirrors import-pihole-image/import-llama-image's own
        # short-circuit: a second run after a successful import must not
        # re-run `docker load` at all.
        content = IMPORT_IMAGE.read_text()
        self.assertIn('if [ -f "$marker" ] && docker image inspect', content)
        self.assertIn("exit 0", content)


class StartSearxngScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(START_SEARXNG)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_reads_image_pinning_from_the_release_scope(self):
        content = START_SEARXNG.read_text()
        self.assertIn("release_root=$(CDPATH= cd -- ", content)
        self.assertIn("image_environment=${release_root}/searxng-image.env", content)

    def test_generates_a_per_device_secret_only_once(self):
        content = START_SEARXNG.read_text()
        self.assertIn('if [ ! -s "$secret_file" ]; then', content)
        self.assertIn("od -An -N32 -tx1 /dev/urandom", content)
        self.assertIn('mv "${secret_file}.tmp" "$secret_file"', content)
        self.assertIn("chmod 0600", content)

    def test_secret_is_passed_as_an_environment_variable_not_a_file(self):
        # SearXNG's own settings loader has no Docker-secrets _FILE
        # convention (confirmed against the real pinned image) -- the
        # secret must be exported for exactly the compose invocation,
        # never written into the compose file or persisted state.
        content = START_SEARXNG.read_text()
        self.assertIn('SEARXNG_SECRET=$(cat "$secret_file") \\', content)
        self.assertNotIn("SEARXNG_SECRET_FILE", content)

    def test_settings_file_is_copied_once_not_overwritten(self):
        content = START_SEARXNG.read_text()
        self.assertIn('if [ ! -s "${config_dir}/settings.yml" ]; then', content)
        self.assertIn("install -m 0644 \"$settings_source\"", content)

    def test_substitutes_the_compose_image_placeholder(self):
        content = START_SEARXNG.read_text()
        self.assertIn("s|@SEARXNG_IMAGE_REFERENCE@|${image_reference}|g", content)

    def test_polls_the_real_homepage_not_a_live_search_query(self):
        # The pinned image ships no Docker HEALTHCHECK (confirmed via
        # `docker inspect`) -- and readiness must never itself perform a
        # real external search on every boot, so the check hits the
        # homepage, not /search.
        content = START_SEARXNG.read_text()
        self.assertIn("http://127.0.0.1:8093/", content)
        self.assertNotIn("/search", content)
        self.assertIn('[ "$attempt" -lt 90 ]', content)
        self.assertIn('test "$healthy" = true', content)
        self.assertIn("searxng-ready", content)


class StopSearxngScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(STOP_SEARXNG)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_stops_the_named_compose_project(self):
        content = STOP_SEARXNG.read_text()
        self.assertIn("--project-name sovereign-searxng", content)
        self.assertIn("stop --timeout 30", content)


class ComposeTemplateTests(unittest.TestCase):
    def test_binds_loopback_only_and_persists_config_and_cache(self):
        content = COMPOSE_TEMPLATE.read_text()
        self.assertIn("image: @SEARXNG_IMAGE_REFERENCE@", content)
        self.assertIn("container_name: sovereign-searxng", content)
        self.assertIn('"127.0.0.1:8093:8080"', content)
        self.assertIn("/data/sovereign/apps/searxng/etc-searxng:/etc/searxng", content)
        self.assertIn("/data/sovereign/apps/searxng/cache-searxng:/var/cache/searxng", content)

    def test_secret_is_interpolated_not_hardcoded(self):
        content = COMPOSE_TEMPLATE.read_text()
        self.assertIn("SEARXNG_SECRET: ${SEARXNG_SECRET}", content)


class SystemdUnitTests(unittest.TestCase):
    def test_artifact_service_verifies_before_import_requires_it(self):
        artifact = ARTIFACT_SERVICE.read_text()
        self.assertIn("ExecStart=/usr/lib/sovereign/verify-searxng-artifact", artifact)
        self.assertIn("RemainAfterExit=yes", artifact)

        import_unit = IMPORT_SERVICE.read_text()
        self.assertIn("Requires=docker.service sovereign-searxng-artifact.service", import_unit)
        self.assertIn("After=docker.service sovereign-searxng-artifact.service", import_unit)
        self.assertIn("ExecStart=/usr/lib/sovereign/import-searxng-image", import_unit)

    def test_searxng_service_requires_import(self):
        searxng = SEARXNG_SERVICE.read_text()
        self.assertIn("Requires=sovereign-searxng-import.service docker.service", searxng)
        self.assertIn("network-online.target", searxng)
        self.assertIn(
            "ExecStart=/opt/sovereign/current/appliance/bin/start-searxng", searxng
        )
        self.assertIn(
            "ExecStop=/opt/sovereign/current/appliance/bin/stop-searxng", searxng
        )
        self.assertIn("RemainAfterExit=yes", searxng)
        self.assertIn("Restart=on-failure", searxng)

    def test_searxng_service_is_ordered_after_provisioning_and_recovery(self):
        # Mirrors sovereign-pihole.service's and sovereign-llama-server
        # .service's own ordering exactly.
        searxng = SEARXNG_SERVICE.read_text()
        self.assertIn("sovereign-imager-provision.service", searxng)
        self.assertIn("sovereign-update-recovery.service", searxng)

        provision = IMAGER_PROVISION_SERVICE.read_text()
        self.assertIn(
            "Before=network-pre.target iwd.service ssh.service sovereign-pihole.service "
            "sovereign-llama-server.service sovereign-searxng.service",
            provision,
        )
        recovery = UPDATE_RECOVERY_SERVICE.read_text()
        self.assertIn(
            "Before=sovereign-pihole.service sovereign-llama-server.service "
            "sovereign-searxng.service",
            recovery,
        )

    def test_all_three_units_are_enabled_in_order(self):
        enablement = ENABLE_UNITS.read_text()
        self.assertIn("sovereign-searxng-artifact.service", enablement)
        self.assertIn("sovereign-searxng-import.service", enablement)
        self.assertIn("sovereign-searxng.service", enablement)
        artifact_index = enablement.index("sovereign-searxng-artifact.service")
        import_index = enablement.index("sovereign-searxng-import.service")
        server_index = enablement.index("sovereign-searxng.service")
        self.assertLess(artifact_index, import_index)
        self.assertLess(import_index, server_index)


class PostBuildEmbeddingTests(unittest.TestCase):
    def test_is_valid_bash(self):
        result = subprocess.run(["bash", "-n", str(POST_BUILD)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_embeds_the_searxng_image_the_same_way_as_pihole_and_llama(self):
        content = POST_BUILD.read_text()
        self.assertIn('. "${SRCROOT}/searxng-image.env"', content)
        self.assertIn('searxng_archive="${artifact_dir}/searxng-arm64.oci.tar"', content)
        self.assertIn(
            'searxng_reference="${SEARXNG_IMAGE_REPOSITORY}@${SEARXNG_IMAGE_DIGEST}"', content
        )
        self.assertIn('"docker://${searxng_reference}"', content)
        self.assertIn(
            '"oci:${searxng_oci_layout}:${SEARXNG_IMAGE_REPOSITORY}:${SEARXNG_IMAGE_TAG}"',
            content,
        )
        self.assertIn(
            'sha256sum "$(basename "$searxng_archive")" > "$(basename "$searxng_archive").sha256"',
            content,
        )

    def test_ships_searxng_image_env_at_base_os_and_release_scope(self):
        content = POST_BUILD.read_text()
        self.assertIn(
            'install -m 0644 "${SRCROOT}/searxng-image.env" \\\n'
            '  "${filesystem}/usr/lib/sovereign/searxng-image.env"',
            content,
        )
        self.assertIn(
            'install -m 0644 "${SRCROOT}/searxng-image.env" \\\n'
            '  "${release_dir}/searxng-image.env"',
            content,
        )

    def test_ships_the_appliance_searxng_directory(self):
        content = POST_BUILD.read_text()
        self.assertIn('"${appliance_dir}/searxng"', content)
        self.assertIn(
            'install -m 0644 "${SRCROOT}/appliance/searxng/compose.yaml.in" \\\n'
            '  "${appliance_dir}/searxng/compose.yaml.in"',
            content,
        )
        self.assertIn(
            'install -m 0644 "${SRCROOT}/appliance/searxng/settings.yml" \\\n'
            '  "${appliance_dir}/searxng/settings.yml"',
            content,
        )


if __name__ == "__main__":
    unittest.main()
