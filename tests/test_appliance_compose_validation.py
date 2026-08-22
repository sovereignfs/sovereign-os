import importlib.util
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
APPLIANCE = ROOT / "image-builder/sovereign/appliance"
DOCKER = shutil.which("docker")

_TEMP_FOR_IMPORT = tempfile.TemporaryDirectory()
os.environ.setdefault("SOVEREIGN_UPDATE_TEST_MODE", "1")
os.environ.setdefault("SOVEREIGN_BASE_OS_RELEASE_PATH", str(Path(_TEMP_FOR_IMPORT.name) / "base-os-release"))
Path(os.environ["SOVEREIGN_BASE_OS_RELEASE_PATH"]).write_text('VERSION="0.1.0-proof.1"\n')
SPEC = importlib.util.spec_from_loader("sovereign_update", SourceFileLoader("sovereign_update", str(CLIENT)))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

FAKE_DIGEST = f"sha256:{'0' * 64}"


class ComposeTemplatesRegistryTests(unittest.TestCase):
    """RFC-0017/0019's IMAGE_COMPONENTS already covers all three embedded
    images (Pi-hole, llama.cpp, SearXNG) -- COMPOSE_TEMPLATES must name the
    same set, or a component silently gets no Compose-template validation
    at release time (the exact gap this change closes for llama/SearXNG)."""

    def test_every_image_component_has_a_compose_template_entry(self):
        image_keys = {key for key, *_ in MODULE.IMAGE_COMPONENTS}
        template_keys = {key for key, *_ in MODULE.COMPOSE_TEMPLATES}
        self.assertEqual(image_keys, template_keys)

    def test_every_referenced_template_file_exists(self):
        for _, template_path, _ in MODULE.COMPOSE_TEMPLATES:
            self.assertTrue(
                (APPLIANCE / template_path).is_file(),
                f"missing Compose template: {template_path}",
            )


class RenderComposeTemplateTests(unittest.TestCase):
    """render_compose_template is the pure-logic half of the release-time
    Compose validation (RFC-0017/RFC-0019's searxng-signed-release
    qualification assessment named this exact gap: a malformed llama or
    SearXNG template previously passed validate_release_payload silently
    and only failed later, at real `docker compose up` time)."""

    def _real_template(self, key):
        template_path = dict((k, t) for k, t, _ in MODULE.COMPOSE_TEMPLATES)[key]
        return (APPLIANCE / template_path).read_text(encoding="utf-8")

    def test_renders_the_real_pihole_template(self):
        rendered = MODULE.render_compose_template(
            "pihole", self._real_template("pihole"), "PIHOLE_IMAGE_REFERENCE",
            f"ghcr.io/example/pihole@{FAKE_DIGEST}",
        )
        self.assertNotIn("@PIHOLE_IMAGE_REFERENCE@", rendered)
        self.assertIn(f"ghcr.io/example/pihole@{FAKE_DIGEST}", rendered)

    def test_renders_the_real_llama_template_substituting_both_placeholders(self):
        # llama's template is the only one with a second placeholder
        # (@LLAMA_MODEL_FILENAME@), substituted by start-llama-server at
        # deploy time rather than release-validation time -- the real
        # regression this guards is a stray, un-substituted @...@ token
        # reaching `docker compose config` silently as a literal string.
        rendered = MODULE.render_compose_template(
            "llama", self._real_template("llama"), "LLAMA_IMAGE_REFERENCE",
            f"ghcr.io/example/llama@{FAKE_DIGEST}",
        )
        self.assertNotIn("@LLAMA_IMAGE_REFERENCE@", rendered)
        self.assertNotIn("@LLAMA_MODEL_FILENAME@", rendered)
        self.assertIn("validation-placeholder.gguf", rendered)

    def test_renders_the_real_searxng_template(self):
        rendered = MODULE.render_compose_template(
            "searxng", self._real_template("searxng"), "SEARXNG_IMAGE_REFERENCE",
            f"ghcr.io/example/searxng@{FAKE_DIGEST}",
        )
        self.assertNotIn("@SEARXNG_IMAGE_REFERENCE@", rendered)
        self.assertIn(f"ghcr.io/example/searxng@{FAKE_DIGEST}", rendered)

    def test_rejects_a_missing_image_placeholder(self):
        with self.assertRaises(MODULE.UpdateError) as caught:
            MODULE.render_compose_template(
                "pihole", "services:\n  pihole:\n    image: pinned\n",
                "PIHOLE_IMAGE_REFERENCE", f"ghcr.io/example/pihole@{FAKE_DIGEST}",
            )
        self.assertEqual("INVALID_COMPOSE_TEMPLATE", caught.exception.code)

    def test_rejects_a_duplicated_image_placeholder(self):
        template = "services:\n  a:\n    image: @PIHOLE_IMAGE_REFERENCE@\n  b:\n    image: @PIHOLE_IMAGE_REFERENCE@\n"
        with self.assertRaises(MODULE.UpdateError) as caught:
            MODULE.render_compose_template(
                "pihole", template, "PIHOLE_IMAGE_REFERENCE",
                f"ghcr.io/example/pihole@{FAKE_DIGEST}",
            )
        self.assertEqual("INVALID_COMPOSE_TEMPLATE", caught.exception.code)

    def test_rejects_a_llama_template_missing_the_model_placeholder(self):
        template = "services:\n  llama-server:\n    image: @LLAMA_IMAGE_REFERENCE@\n"
        with self.assertRaises(MODULE.UpdateError) as caught:
            MODULE.render_compose_template(
                "llama", template, "LLAMA_IMAGE_REFERENCE",
                f"ghcr.io/example/llama@{FAKE_DIGEST}",
            )
        self.assertEqual("INVALID_COMPOSE_TEMPLATE", caught.exception.code)


@unittest.skipIf(DOCKER is None, "docker is unavailable")
class RealDockerComposeValidationTests(unittest.TestCase):
    """The actual defect this change closes: llama's and SearXNG's own
    Compose templates were never run through `docker compose config`
    before activation, unlike Pi-hole's. These tests use the real docker
    binary (not a fake stub), since a fake stub that always exits 0 cannot
    tell a syntactically valid template from a broken one -- that
    distinction is the entire point of this check."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def _render(self, key):
        template_path = dict((k, t) for k, t, _ in MODULE.COMPOSE_TEMPLATES)[key]
        placeholder = dict((k, p) for k, _, p in MODULE.COMPOSE_TEMPLATES)[key]
        template = (APPLIANCE / template_path).read_text(encoding="utf-8")
        return MODULE.render_compose_template(
            key, template, placeholder, f"ghcr.io/example/{key}@{FAKE_DIGEST}"
        )

    def _validate(self, compose_text, extra_env=None):
        compose = self.directory / "compose.yaml"
        compose.write_text(compose_text, encoding="utf-8")
        env = {**os.environ, **(extra_env or {})}
        return subprocess.run(
            [DOCKER, "compose", "--file", str(compose), "config", "--quiet"],
            env=env, capture_output=True, timeout=30,
        )

    def test_the_real_pihole_template_passes(self):
        result = self._validate(self._render("pihole"))
        self.assertEqual(0, result.returncode, result.stderr.decode())

    def test_the_real_llama_template_passes(self):
        result = self._validate(self._render("llama"))
        self.assertEqual(0, result.returncode, result.stderr.decode())

    def test_the_real_searxng_template_passes(self):
        # Mirrors start-searxng's own real invocation shape: SEARXNG_SECRET
        # is exported for this one `docker compose` call, never persisted.
        result = self._validate(self._render("searxng"), {"SEARXNG_SECRET": "0" * 64})
        self.assertEqual(0, result.returncode, result.stderr.decode())

    def test_a_structurally_broken_template_is_rejected(self):
        # The real regression this check exists to catch: a template edit
        # that is well-formed YAML but not a valid Compose document (here,
        # `ports` given a scalar instead of a list) previously would have
        # passed validate_release_payload for llama/SearXNG and only
        # failed later, at real `docker compose up` time on a device.
        broken = (
            "services:\n"
            "  broken:\n"
            f"    image: ghcr.io/example/broken@{FAKE_DIGEST}\n"
            "    ports: \"not-a-list\"\n"
        )
        result = self._validate(broken)
        self.assertNotEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
