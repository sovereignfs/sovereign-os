import importlib.util
import os
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLIENT = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/usr/sbin/sovereign-update"
)

_TEMP_FOR_IMPORT = tempfile.TemporaryDirectory()
os.environ.setdefault("SOVEREIGN_UPDATE_TEST_MODE", "1")
os.environ.setdefault("SOVEREIGN_BASE_OS_RELEASE_PATH", str(Path(_TEMP_FOR_IMPORT.name) / "base-os-release"))
Path(os.environ["SOVEREIGN_BASE_OS_RELEASE_PATH"]).write_text('VERSION="0.1.0-proof.1"\n')
SPEC = importlib.util.spec_from_loader("sovereign_update", SourceFileLoader("sovereign_update", str(CLIENT)))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CompareVersionsChannelOrderingTests(unittest.TestCase):
    """A device on a proof.N base-OS version must be able to accept a real
    preview.N release -- plain semver prerelease comparison gets this
    backwards, since "proof" sorts after "preview" alphabetically. See the
    second-base-os-update-hardware-qualification-report.md finding this
    covers."""

    def test_proof_sorts_before_preview(self):
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-proof.1", "0.1.0-preview.1"))
        self.assertEqual(1, MODULE.compare_versions("0.1.0-preview.1", "0.1.0-proof.1"))

    def test_proof_sorts_before_preview_regardless_of_trailing_numbers(self):
        # The exact real-world case the qualification pass hit: a device on
        # proof.1 must treat any preview.N as newer, not just preview.1.
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-proof.99", "0.1.0-preview.1"))

    def test_preview_sorts_before_rc_and_stable(self):
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-preview.1", "0.1.0-rc.1"))
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-rc.1", "0.1.0-stable.1"))
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-proof.1", "0.1.0-stable.1"))

    def test_same_channel_still_compares_numerically(self):
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-proof.1", "0.1.0-proof.2"))
        self.assertEqual(1, MODULE.compare_versions("0.1.0-proof.10", "0.1.0-proof.2"))
        self.assertEqual(0, MODULE.compare_versions("0.1.0-proof.1", "0.1.0-proof.1"))

    def test_unknown_channel_words_fall_back_to_lexical_comparison(self):
        # Neither word is in PRERELEASE_CHANNEL_ORDER -- must not crash, and
        # must fall back to the original plain-lexical behavior rather than
        # silently mis-ordering something this table doesn't know about.
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-alpha.1", "0.1.0-beta.1"))

    def test_release_core_still_dominates_prerelease_channel(self):
        # A newer release-core version always wins regardless of channel
        # word, exactly as before this fix.
        self.assertEqual(-1, MODULE.compare_versions("0.1.0-stable.1", "0.2.0-proof.1"))


if __name__ == "__main__":
    unittest.main()
