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

VERIFY_ARTIFACT = OVERLAY / "usr/lib/sovereign/verify-llama-artifact"
IMPORT_IMAGE = OVERLAY / "usr/lib/sovereign/import-llama-image"
START_SERVER = APPLIANCE / "bin/start-llama-server"
STOP_SERVER = APPLIANCE / "bin/stop-llama-server"
COMPOSE_TEMPLATE = APPLIANCE / "llama/compose.yaml.in"
MODEL_ENV = APPLIANCE / "llama/model.env"
LLAMA_IMAGE_ENV = SOVEREIGN_DIR / "llama-image.env"
ARTIFACT_SERVICE = OVERLAY / "etc/systemd/system/sovereign-llama-artifact.service"
IMPORT_SERVICE = OVERLAY / "etc/systemd/system/sovereign-llama-import.service"
SERVER_SERVICE = OVERLAY / "etc/systemd/system/sovereign-llama-server.service"
CONVERSATION_SERVICE = OVERLAY / "etc/systemd/system/sovereign-conversation.service"
IMAGER_PROVISION_SERVICE = OVERLAY / "etc/systemd/system/sovereign-imager-provision.service"
UPDATE_RECOVERY_SERVICE = OVERLAY / "etc/systemd/system/sovereign-update-recovery.service"
POST_BUILD = SOVEREIGN_DIR / "post-build.sh"


class LlamaImageEnvTests(unittest.TestCase):
    def test_pins_a_complete_digest_for_the_selected_runner(self):
        content = LLAMA_IMAGE_ENV.read_text()
        self.assertIn("LLAMA_IMAGE_REPOSITORY='ghcr.io/ggml-org/llama.cpp'", content)
        self.assertIn("LLAMA_IMAGE_TAG='server'", content)
        match = re.search(r"LLAMA_IMAGE_DIGEST='sha256:([0-9a-f]+)'", content)
        self.assertIsNotNone(match)
        self.assertEqual(64, len(match.group(1)))
        self.assertIn("LLAMA_IMAGE_PLATFORM='linux/arm64'", content)


class ModelEnvTests(unittest.TestCase):
    def test_pins_a_complete_digest_for_adr_0013s_selected_model(self):
        content = MODEL_ENV.read_text()
        self.assertIn("LLAMA_MODEL_FILENAME='qwen2.5-3b-instruct-q4_k_m.gguf'", content)
        self.assertIn(
            "LLAMA_MODEL_URL='https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/"
            "resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf'",
            content,
        )
        match = re.search(r"LLAMA_MODEL_SHA256='([0-9a-f]+)'", content)
        self.assertIsNotNone(match)
        self.assertEqual(64, len(match.group(1)))
        self.assertIn("LLAMA_MODEL_SIZE_BYTES='2104932768'", content)


class VerifyArtifactScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(VERIFY_ARTIFACT)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_verifies_checksum_and_archive_contents_before_marking_ready(self):
        content = VERIFY_ARTIFACT.read_text()
        self.assertIn(". /usr/lib/sovereign/llama-image.env", content)
        self.assertIn('sha256sum -c "${archive}.sha256"', content)
        self.assertIn('tar -tf "$archive" | grep -Fx "oci-layout"', content)
        self.assertIn('tar -tf "$archive" | grep -Fx "index.json"', content)
        self.assertIn("blobs/sha256/${manifest_digest}", content)
        self.assertIn("/data/sovereign/llama-artifact-ready", content)


class ImportImageScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(IMPORT_IMAGE)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_loads_tags_and_verifies_platform_before_marking_ready(self):
        content = IMPORT_IMAGE.read_text()
        self.assertIn(". /usr/lib/sovereign/llama-image.env", content)
        self.assertIn("docker load --input", content)
        self.assertIn('docker image tag "$LLAMA_IMAGE_DIGEST" "$image"', content)
        self.assertIn('test "$platform" = "$LLAMA_IMAGE_PLATFORM"', content)
        self.assertIn("marker=${state_dir}/llama-import-ready", content)
        self.assertIn('mv "${marker}.tmp" "$marker"', content)

    def test_is_idempotent_when_already_imported(self):
        # Mirrors import-pihole-image's own short-circuit: a second run
        # after a successful import must not re-run `docker load` at all.
        content = IMPORT_IMAGE.read_text()
        self.assertIn('if [ -f "$marker" ] && docker image inspect', content)
        self.assertIn("exit 0", content)


class StartLlamaServerScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(START_SERVER)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_reads_image_and_model_pinning_from_the_right_scopes(self):
        content = START_SERVER.read_text()
        # llama-image.env comes from the release root (mirrors
        # start-pihole reading pihole-image.env the same way) -- the
        # model pin is appliance-scoped, not base-OS-embedded.
        self.assertIn("release_root=$(CDPATH= cd -- ", content)
        self.assertIn('image_environment=${release_root}/llama-image.env', content)
        self.assertIn('model_environment=${appliance_root}/llama/model.env', content)

    def test_downloads_the_model_only_when_missing_or_invalid(self):
        content = START_SERVER.read_text()
        self.assertIn('if [ ! -s "$model_file" ] || ! verify_model; then', content)
        self.assertIn('sha256sum -c -', content)

    def test_download_is_atomic_and_re_verified_before_use(self):
        content = START_SERVER.read_text()
        self.assertIn('--output "${model_file}.tmp"', content)
        self.assertIn('mv "${model_file}.tmp" "$model_file"', content)
        self.assertIn("if ! verify_model; then", content)
        self.assertIn('rm -f "$model_file"', content)
        self.assertIn("digest verification", content)

    def test_model_directory_is_under_data_not_the_release(self):
        content = START_SERVER.read_text()
        self.assertIn("model_dir=${state_dir}/models", content)
        self.assertIn("state_dir=/data/sovereign", content)

    def test_substitutes_both_compose_placeholders(self):
        content = START_SERVER.read_text()
        self.assertIn("s|@LLAMA_IMAGE_REFERENCE@|${image_reference}|g", content)
        self.assertIn("s|@LLAMA_MODEL_FILENAME@|${LLAMA_MODEL_FILENAME}|g", content)

    def test_polls_the_real_health_endpoint_before_marking_ready(self):
        content = START_SERVER.read_text()
        self.assertIn('http://127.0.0.1:8081/health', content)
        self.assertIn('[ "$attempt" -lt 90 ]', content)
        self.assertIn('test "$healthy" = true', content)
        self.assertIn("llama-server-ready", content)


class StopLlamaServerScriptTests(unittest.TestCase):
    def test_is_valid_posix_shell(self):
        result = subprocess.run(["sh", "-n", str(STOP_SERVER)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_stops_the_named_compose_project(self):
        content = STOP_SERVER.read_text()
        self.assertIn("--project-name sovereign-llama-server", content)
        self.assertIn("stop --timeout 30", content)


class ComposeTemplateTests(unittest.TestCase):
    def test_binds_loopback_only_and_mounts_models_read_only(self):
        content = COMPOSE_TEMPLATE.read_text()
        self.assertIn("image: @LLAMA_IMAGE_REFERENCE@", content)
        self.assertIn('container_name: sovereign-llama-server', content)
        self.assertIn('"127.0.0.1:8081:8080"', content)
        self.assertIn("/data/sovereign/models:/models:ro", content)
        self.assertIn("/models/@LLAMA_MODEL_FILENAME@", content)


class SystemdUnitTests(unittest.TestCase):
    def test_artifact_service_verifies_before_import_requires_it(self):
        artifact = ARTIFACT_SERVICE.read_text()
        self.assertIn("ExecStart=/usr/lib/sovereign/verify-llama-artifact", artifact)
        self.assertIn("RemainAfterExit=yes", artifact)

        import_unit = IMPORT_SERVICE.read_text()
        self.assertIn("Requires=docker.service sovereign-llama-artifact.service", import_unit)
        self.assertIn("After=docker.service sovereign-llama-artifact.service", import_unit)
        self.assertIn("ExecStart=/usr/lib/sovereign/import-llama-image", import_unit)

    def test_server_service_requires_import_and_tolerates_a_slow_first_download(self):
        server = SERVER_SERVICE.read_text()
        self.assertIn("Requires=sovereign-llama-import.service docker.service", server)
        self.assertIn("network-online.target", server)
        self.assertIn("TimeoutStartSec=0", server)
        self.assertIn(
            "ExecStart=/opt/sovereign/current/appliance/bin/start-llama-server", server
        )
        self.assertIn(
            "ExecStop=/opt/sovereign/current/appliance/bin/stop-llama-server", server
        )
        self.assertIn("RemainAfterExit=yes", server)
        self.assertIn("Restart=on-failure", server)

    def test_server_service_is_ordered_after_provisioning_and_recovery(self):
        # Mirrors sovereign-pihole.service's own ordering exactly -- both
        # generic device-provisioning steps must complete before any app
        # service (Pi-hole or llama-server) starts.
        server = SERVER_SERVICE.read_text()
        self.assertIn("sovereign-imager-provision.service", server)
        self.assertIn("sovereign-update-recovery.service", server)

        provision = IMAGER_PROVISION_SERVICE.read_text()
        self.assertIn(
            "Before=network-pre.target iwd.service ssh.service sovereign-pihole.service "
            "sovereign-llama-server.service",
            provision,
        )
        recovery = UPDATE_RECOVERY_SERVICE.read_text()
        self.assertIn("Before=sovereign-pihole.service sovereign-llama-server.service", recovery)

    def test_conversation_service_depends_softly_on_llama_server(self):
        conversation = CONVERSATION_SERVICE.read_text()
        self.assertIn("sovereign-llama-server.service", conversation)
        after_line = next(
            line for line in conversation.splitlines() if line.startswith("After=")
        )
        self.assertIn("sovereign-llama-server.service", after_line)
        requires_lines = [
            line for line in conversation.splitlines() if line.startswith("Requires=")
        ]
        self.assertFalse(
            any("sovereign-llama-server.service" in line for line in requires_lines),
            "must be a soft After= dependency, not Requires=",
        )

    def test_all_three_units_are_enabled(self):
        enablement = ENABLE_UNITS.read_text()
        self.assertIn("sovereign-llama-artifact.service", enablement)
        self.assertIn("sovereign-llama-import.service", enablement)
        self.assertIn("sovereign-llama-server.service", enablement)
        self.assertIn("sovereign-conversation.service", enablement)
        # Artifact must be enabled before import, and import before the
        # server -- enable-units order does not itself enforce systemd
        # ordering (After=/Requires= already do), but keeping the file's
        # own order consistent with Pi-hole's equivalent block avoids
        # misleading future readers.
        artifact_index = enablement.index("sovereign-llama-artifact.service")
        import_index = enablement.index("sovereign-llama-import.service")
        server_index = enablement.index("sovereign-llama-server.service")
        self.assertLess(artifact_index, import_index)
        self.assertLess(import_index, server_index)


class PostBuildEmbeddingTests(unittest.TestCase):
    def test_is_valid_bash(self):
        result = subprocess.run(["bash", "-n", str(POST_BUILD)], capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)

    def test_embeds_the_llama_image_the_same_way_as_pihole(self):
        content = POST_BUILD.read_text()
        self.assertIn('. "${SRCROOT}/llama-image.env"', content)
        self.assertIn('llama_archive="${artifact_dir}/llama-arm64.oci.tar"', content)
        self.assertIn(
            'llama_reference="${LLAMA_IMAGE_REPOSITORY}@${LLAMA_IMAGE_DIGEST}"', content
        )
        self.assertIn('"docker://${llama_reference}"', content)
        self.assertIn(
            '"oci:${llama_oci_layout}:${LLAMA_IMAGE_REPOSITORY}:${LLAMA_IMAGE_TAG}"', content
        )
        self.assertIn(
            'sha256sum "$(basename "$llama_archive")" > "$(basename "$llama_archive").sha256"',
            content,
        )

    def test_ships_llama_image_env_at_base_os_and_release_scope(self):
        content = POST_BUILD.read_text()
        self.assertIn(
            'install -m 0644 "${SRCROOT}/llama-image.env" \\\n'
            '  "${filesystem}/usr/lib/sovereign/llama-image.env"',
            content,
        )
        self.assertIn(
            'install -m 0644 "${SRCROOT}/llama-image.env" \\\n'
            '  "${release_dir}/llama-image.env"',
            content,
        )

    def test_ships_the_appliance_llama_directory(self):
        content = POST_BUILD.read_text()
        self.assertIn('"${appliance_dir}/llama"', content)
        self.assertIn(
            'install -m 0644 "${SRCROOT}/appliance/llama/compose.yaml.in" \\\n'
            '  "${appliance_dir}/llama/compose.yaml.in"',
            content,
        )
        self.assertIn(
            'install -m 0644 "${SRCROOT}/appliance/llama/model.env" \\\n'
            '  "${appliance_dir}/llama/model.env"',
            content,
        )


if __name__ == "__main__":
    unittest.main()
