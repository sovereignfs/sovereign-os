import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
)
LAYER = ROOT / "image-builder/sovereign/layer/sovereign-proof.yaml"
ENABLE_UNITS = (
    ROOT
    / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
)


class PhysicalQualificationFixTests(unittest.TestCase):
    def test_data_partition_expands_before_persistent_services(self):
        script = (OVERLAY / "usr/lib/sovereign/expand-data-partition").read_text()
        service = (
            OVERLAY / "etc/systemd/system/sovereign-data-expand.service"
        ).read_text()
        docker_drop_in = (
            OVERLAY
            / "etc/systemd/system/docker.service.d/10-sovereign-data.conf"
        ).read_text()
        containerd_drop_in = (
            OVERLAY
            / "etc/systemd/system/containerd.service.d/10-sovereign-data.conf"
        ).read_text()

        self.assertIn("cloud-guest-utils", LAYER.read_text())
        self.assertIn("sovereign-data-expand.service", ENABLE_UNITS.read_text())
        self.assertIn('growpart "$parent_device" "$partition_number"', script)
        self.assertIn('resize2fs "$source_device"', script)
        self.assertIn('mv "${marker}.tmp" "$marker"', script)
        self.assertIn("Before=sovereign-proof.service containerd.service docker.service", service)
        self.assertIn("Requires=sovereign-data-expand.service", docker_drop_in)
        self.assertIn("Requires=sovereign-data-expand.service", containerd_drop_in)

    def test_unconfigured_wifi_does_not_block_network_online(self):
        network = (
            OVERLAY / "etc/systemd/network/02-wlan0.network"
        ).read_text()
        self.assertIn("Name=wlan0", network)
        self.assertIn("RequiredForOnline=no", network)

    def test_pihole_secret_name_and_authenticated_readiness(self):
        compose = (
            OVERLAY / "usr/lib/sovereign/pihole/compose.yaml.in"
        ).read_text()
        start = (OVERLAY / "usr/lib/sovereign/start-pihole").read_text()

        self.assertIn("WEBPASSWORD_FILE: pihole_webpasswd", compose)
        self.assertNotIn("WEBPASSWORD_FILE: /run/secrets/", compose)
        self.assertIn("http://127.0.0.1:8080/api/auth", start)
        self.assertIn("json.dump", start)
        self.assertRegex(start, r'grep -Eq .*valid.*true')
        self.assertIn("credential=pass", start)

    def test_dns_slash_redirect_and_absolute_redirect_verification(self):
        nginx = (OVERLAY / "etc/nginx/sites-available/sovereign").read_text()
        verifier = (OVERLAY / "usr/lib/sovereign/verify-local-access").read_text()
        service = (
            OVERLAY / "etc/systemd/system/sovereign-local-access.service"
        ).read_text()

        self.assertIn("location = /dns/", nginx)
        self.assertIn("return 308 /dns/admin/;", nginx)
        self.assertIn("%{redirect_url}", verifier)
        self.assertIn("http://127.0.0.1/dns/admin/", verifier)
        self.assertNotIn("^location: /dns/admin/", verifier)
        self.assertIn("dns_redirect=pass", verifier)
        self.assertIn("StartLimitBurst=6", service)


if __name__ == "__main__":
    unittest.main()
