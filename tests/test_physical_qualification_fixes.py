import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = (
    ROOT
    / "image-builder/sovereign/layer/sovereign-proof.rootfs-overlay"
)
APPLIANCE = ROOT / "image-builder/sovereign/appliance"
LAYER = ROOT / "image-builder/sovereign/layer/sovereign-proof.yaml"
ENABLE_UNITS = (
    ROOT
    / "image-builder/sovereign/image/sovereign-data/bdebstrap/customize90-sovereign"
)
ENABLE_UNITS_AB = (
    ROOT
    / "image-builder/sovereign/image/sovereign-ab-data/bdebstrap/customize90-sovereign-ab"
)
DATA_IMAGE_YAML = ROOT / "image-builder/sovereign/image/sovereign-data/image.yaml"
AB_DATA_IMAGE_YAML = ROOT / "image-builder/sovereign/image/sovereign-ab-data/image.yaml"


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
            APPLIANCE / "pihole/compose.yaml.in"
        ).read_text()
        start = (APPLIANCE / "bin/start-pihole").read_text()

        self.assertIn("WEBPASSWORD_FILE: pihole_webpasswd", compose)
        self.assertNotIn("WEBPASSWORD_FILE: /run/secrets/", compose)
        self.assertIn("http://127.0.0.1:8080/api/auth", start)
        self.assertIn("json.dump", start)
        self.assertRegex(start, r'grep -Eq .*valid.*true')
        self.assertIn("credential=pass", start)

    def test_dns_slash_redirect_and_absolute_redirect_verification(self):
        nginx = (APPLIANCE / "nginx/sovereign.conf").read_text()
        verifier = (APPLIANCE / "bin/verify-local-access").read_text()
        service = (
            OVERLAY / "etc/systemd/system/sovereign-local-access.service"
        ).read_text()

        self.assertIn("location = /dns/", nginx)
        self.assertIn("return 308 /dns/admin/;", nginx)
        self.assertIn("%{redirect_url}", verifier)
        self.assertIn("http://127.0.0.1/dns/admin/", verifier)
        self.assertNotIn("^location: /dns/admin/", verifier)
        self.assertIn("dns_redirect=pass", verifier)
        self.assertIn('until curl --fail --silent --show-error', verifier)
        self.assertIn('[ "$attempt" -lt 30 ] || exit 1', verifier)
        self.assertIn("sleep 1", verifier)
        self.assertIn("StartLimitBurst=6", service)

    def test_pihole_ui_boot_check_expects_the_adr_0010_signin_gate(self):
        # verify-local-access previously expected to reach real Pi-hole
        # content unauthenticated at /dns/admin/; ADR-0010 gates that path,
        # so the boot check must now expect the sign-in redirect instead --
        # otherwise this readiness check would silently stop verifying
        # anything real about that path.
        verifier = (APPLIANCE / "bin/verify-local-access").read_text()

        self.assertIn(
            'http://127.0.0.1/console/?next=/dns/admin/', verifier
        )
        self.assertIn("pihole_gate=pass", verifier)
        self.assertNotIn("pihole_ui=pass", verifier)
        self.assertNotIn(
            "curl --fail --silent --show-error --max-time 10 \\\n  --output /dev/null http://127.0.0.1/dns/admin/",
            verifier,
        )

    def test_update_health_gate_expects_the_adr_0010_signin_gate(self):
        # sovereign-update's activate/trial health gate (ADR-0009's rollback
        # safety net) previously expected real Pi-hole content at
        # /dns/admin/ unauthenticated. `curl --fail` treats a 3xx the same
        # as a 2xx, so this check would have kept silently "passing" against
        # the new redirect without ever confirming the gate is actually the
        # thing being hit -- comparing the redirect target directly closes
        # that gap in either direction (missing gate or broken gate).
        verifier = (APPLIANCE / "bin/verify-update-health").read_text()

        self.assertIn(
            'http://127.0.0.1/console/?next=/dns/admin/', verifier
        )
        self.assertIn("redirect_url", verifier)
        self.assertNotIn(
            "curl --fail --silent --show-error --max-time 10 \\\n"
            "    --output /dev/null http://127.0.0.1/dns/admin/",
            verifier,
        )

    def test_root_redirect_and_console_checks_retry_instead_of_racing_startup(self):
        # nginx and sovereign-console.service both just (re)started when
        # this script runs -- an unretried curl here can race a backend
        # that isn't listening yet. Confirmed on real hardware (ADR-0009
        # qualification, attempt 8): sovereign-update install restarts
        # everything back-to-back during activation, giving these checks
        # far less natural settle time than a cold boot would, and the
        # unretried root_redirect/console checks failed with a transient
        # 404 as a direct result.
        verifier = (APPLIANCE / "bin/verify-local-access").read_text()
        lines = verifier.splitlines()
        nginx_t_index = next(i for i, line in enumerate(lines) if line.strip() == "nginx -t")
        health_until_index = next(
            i for i, line in enumerate(lines)
            if "curl --fail --silent --show-error --max-time 10 \\" in line
            and i > nginx_t_index
            and lines[i + 1].strip() == "http://127.0.0.1/api/v1/health | \\"
        )
        between = "\n".join(lines[nginx_t_index:health_until_index])
        self.assertIn("until", between)
        self.assertIn("http://127.0.0.1/console/", between)

    def test_eth0_uses_dhclient_not_networkds_own_dhcp_client(self):
        # systemd-networkd's own DHCPv4 client reliably fails with
        # ENOMEDIUM on the qualification hardware despite a stable
        # carrier -- hardware-verified across warm reboots, hard power
        # cycles, and manual retries well after boot (see
        # docs/research/eth0-dhcp-carrier-race-finding.md). ISC dhclient,
        # exercising the same underlying raw-socket DHCP exchange via a
        # different code path, acquired a real lease immediately and
        # reliably every time -- confirming the interface, driver, and
        # router-side DHCP server are all fully functional, and this is
        # a systemd-networkd-specific bug being routed around.
        network = (OVERLAY / "etc/systemd/network/01-eth0.network").read_text()
        self.assertIn("Name=eth0", network)
        self.assertIn("DHCP=no", network)
        self.assertIn("RequiredForOnline=no", network)

        service = (
            OVERLAY / "etc/systemd/system/sovereign-eth0-dhclient.service"
        ).read_text()
        self.assertIn("Type=oneshot", service)
        self.assertIn("RemainAfterExit=yes", service)
        self.assertIn("Before=network-online.target", service)
        self.assertIn(
            "ExecStart=/usr/sbin/dhclient -4 -sf /usr/sbin/dhclient-script", service
        )
        self.assertIn("ExecStop=/usr/sbin/dhclient -x", service)

        # Both today's single-root production image and the RFC-0016
        # A/B image need this fix -- it's not layout-specific.
        self.assertIn("sovereign-eth0-dhclient.service", ENABLE_UNITS.read_text())
        self.assertIn("sovereign-eth0-dhclient.service", ENABLE_UNITS_AB.read_text())
        self.assertIn("isc-dhcp-client", DATA_IMAGE_YAML.read_text())
        self.assertIn("isc-dhcp-client", AB_DATA_IMAGE_YAML.read_text())


if __name__ == "__main__":
    unittest.main()
