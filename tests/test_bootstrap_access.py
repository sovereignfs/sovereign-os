import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize30-bootstrap-access"
SSH_CONFIG = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay/etc/ssh/sshd_config.d/10-sovereign.conf"
)
LAYER_CONFIG = ROOT / "image-builder/sovereign/layer/sovereign-proof.yaml"


class BootstrapAccessTests(unittest.TestCase):
    def test_preview_account_contract(self):
        hook = HOOK.read_text()
        self.assertIn("username=sovereign", hook)
        self.assertIn("--uid 1000", hook)
        self.assertIn("--groups sudo", hook)
        self.assertIn("chage --lastday 0", hook)

        match = re.search(r"password_hash='([^']+)'", hook)
        self.assertIsNotNone(match)
        generated = subprocess.run(
            ["openssl", "passwd", "-6", "-salt", "sovereign-preview", "sovereign"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        self.assertEqual(generated, match.group(1))

    def test_password_login_is_lan_bootstrap_default(self):
        config = SSH_CONFIG.read_text()
        self.assertIn("PermitRootLogin no", config)
        self.assertIn("PasswordAuthentication yes", config)

    def test_operator_can_use_documented_sudo_flow(self):
        self.assertRegex(LAYER_CONFIG.read_text(), r"(?m)^    - sudo$")


if __name__ == "__main__":
    unittest.main()
