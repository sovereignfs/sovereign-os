# Research: systemd-networkd DHCP client fails with ENOMEDIUM on eth0 despite a stable carrier

**Status:** Concluded — fixed (workaround shipped; upstream kernel/systemd-networkd root cause still unknown)
**Author:** Claude (with kasunben), during RFC-0016 hardware qualification
**Started:** 2026-08-03
**Concluded:** 2026-08-04
**Decision informed:** `image-builder/sovereign/layer/sovereign-proof.rootfs-overlay` now ships `01-eth0.network` + `sovereign-eth0-dhclient.service`, disabling systemd-networkd's own DHCPv4 client for `eth0` in favor of ISC `dhclient` — applied to both the production single-root image and the RFC-0016 A/B image

## Question

Why did the qualification Raspberry Pi 5 lose all IPv4 connectivity (no address on `eth0`, no default route, DNS/internet unreachable) partway through today's RFC-0016 hardware session, and why did it persist across a warm reboot, a hard power cycle, and manual `networkctl reconfigure` attempts?

## Context

This surfaced indirectly: a base-OS `tryboot` trial's health check failed because Pi-hole's `gravity.db` didn't exist, which traced back to Pi-hole's `gravity.sh` being unable to reach the internet to download blocklists, which traced back to `eth0` having no IPv4 address at all. The device had been reachable over SSH the entire time via IPv6 link-local address resolution (`fe80::...%eth0`, advertised over mDNS), which does not require DHCP — this is why the loss of IPv4 connectivity went unnoticed until Pi-hole's health check (which needs real internet access) failed.

## Sources and Environment

- Raspberry Pi 5, qualification device, running the `sovereign-ab-proof` image (RFC-0016).
- `systemd 257 (257.13-1~deb13u1)`, kernel `6.18.39+rpt-rpi-2712`.
- NIC: onboard `macb` driver (Cadence GEM), PHY `Broadcom BCM54213PE`, 1000BASE-T.
- `/etc/systemd/network/01-eth0.network` on this image is **not** sourced from this repo's `image-builder` layers (confirmed via `grep -rl` across `image-builder/`) — it ships from an upstream Raspberry Pi/Debian package default (`[Match] Name=eth0` / `[Network] DHCP=yes`), not something Sovereign's own overlays currently touch.

## Findings

Separating what was directly observed from what was inferred.

**Observed:**

- `ip addr show eth0` showed only an IPv6 link-local address; no IPv4, no default route (`ip route` had only Docker's internal bridge routes).
- `journalctl -u systemd-networkd` showed, consistently across a warm reboot and a hard power cycle:
  ```
  eth0: Gained carrier
  eth0: Failed to configure DHCPv4 client: No medium found
  eth0: Failed
  eth0: Trying to reconfigure the interface.
  ... (repeats ~5-6 times within the same second)
  eth0: The interface entered the failed state frequently, refusing to reconfigure it automatically.
  ```
- Kernel/sysfs state contradicted the driver's own DHCP failure: `/sys/class/net/eth0/carrier` = `1`, `operstate` = `up`, `speed` = `1000`, `carrier_changes` = `1` (exactly one clean down→up transition since boot, no flapping). `dmesg` showed a clean link-up at boot: `macb ... eth0: Link is Up - 1Gbps/Full - flow control tx`.
- The user physically checked the Ethernet cable and switch port; both were seated correctly. This, combined with the sysfs/dmesg evidence above, rules out a physical-layer cause.
- Manually assigning a static IPv4 address (`ip addr add 192.168.50.220/24 dev eth0` + a manual default route) worked immediately and perfectly — full connectivity, 0% packet loss, working DNS resolution. This proves the interface, cable, switch port, and kernel driver are all fully functional; the fault is isolated to systemd-networkd's DHCP client startup path specifically.
- Persisting that static config in `/etc/systemd/network/01-eth0.network` (with `IPv6AcceptRA=no` added) survived a real reboot and restored full connectivity automatically.
- Critically: a follow-up test with `DHCP=yes` + `IPv6AcceptRA=no` (i.e., keep DHCP, only disable the IPv6 RA/DHCPv6 path) **still failed** — DHCPv4 itself did not acquire an address. The very first failure observed (before any changes were made) was also specifically `Failed to configure DHCPv4 client: No medium found`, not a DHCPv6 issue.

**Inferred (not directly proven):**

- The error is a genuine kernel-reported `ENOMEDIUM` ("No medium found"), returned to *whichever* DHCP client (v4 or v6) systemd-networkd starts first, at a specific timing window right after the `Gained carrier` event — before the driver/kernel state is fully settled for socket-level operations, even though the carrier bit and operstate are already correct by the time anything reads them a moment later.
- Because systemd-networkd's automatic retry loop re-attempts a handful of times within the same second and then permanently backs off ("entered the failed state frequently, refusing to reconfigure it automatically"), the retries don't span enough wall-clock time to outlast whatever brief window the race occupies — a longer, spaced-out retry (or a fixed startup delay before the first DHCP attempt) might succeed where systemd-networkd's built-in backoff does not. This was not tested directly.
- This is most likely a systemd-networkd/kernel/`macb` driver interaction bug, not anything specific to Sovereign's own configuration — the affected `.network` file is an upstream default, and nothing in this session's work (RFC-0016 or otherwise) touches networking configuration.

## Alternatives

- **Static IP per-device:** what's currently applied to the qualification device. Works, but is not viable as a general fix — every real deployed device is on a different network/subnet, so a hardcoded address can't ship in the image.
- **`IPv6AcceptRA=no` alone:** tested and rejected — does not fix the DHCPv4 case, only avoids the bug for configs (like a static IP) that never invoke any DHCP client at all.
- **Startup delay / custom retry policy before DHCPv4 client start:** not yet tested. Plausible given the race-condition framing above, but unverified.
- **Alternative DHCP client (`dhclient`, `udhcpc`, `dhcpcd`):** not testable on this device — none of these are installed, and installing one wasn't attempted (out of scope for this session's finding, would need its own evaluation of which client to standardize on).

## Limitations

- No alternative DHCP client was available on-device to test whether the bug is specific to systemd-networkd's own implementation or a more general kernel/driver issue that any DHCP client would hit.
- No `ethtool` available on-device for lower-level PHY/link diagnostics beyond what `dmesg`/sysfs already provided.
- The exact trigger for *why* this reproduced today, after presumably working correctly for the 22+ hours the device had been running before this session's heavy reboot/tryboot/power-cycle cycling, is not established. It's possible this bug has always been latent and simply never triggered before, or that something about repeated rapid reboots specifically increases the odds of hitting the race — this session's evidence can't distinguish between those.

## Resolution (2026-08-04)

The third unresolved question above was tested directly and answered: **yes**, a different DHCP client implementation sidesteps the bug entirely. Research into public reports (Raspberry Pi kernel issue tracker, a `ftgmac100` driver patch fixing a similar race on different hardware) turned up no exact match or known fix for this precise `macb`/`ENOMEDIUM` signature, but did surface a plausible general mechanism: PHY link-up can trigger an `adjust_link`-style MAC reconfiguration in some drivers that races against whatever tries to use the interface immediately afterward. No upstream fix was found or attempted — this remains a kernel/systemd-networkd-level mystery.

Directly on the qualification device (root filesystem read-only, so `apt-get install` couldn't write to `/usr/sbin` — packages were extracted from the cached `.deb`s with `dpkg-deb -x` into a writable path instead):

- `ethtool --show-eee eth0` showed EEE (Energy Efficient Ethernet) `enabled - inactive` on this BCM54213PE PHY, a chip with several public reports of EEE-related instability on Raspberry Pi 5 — investigated as a candidate cause but not tested in isolation, since the `dhclient` test (below) resolved the problem before this line of investigation was needed.
- ISC `dhclient -1 -v -d eth0`, run standalone without touching the working static-IP config, acquired a real lease (`DHCPDISCOVER` → `DHCPOFFER` → `DHCPREQUEST` → `DHCPACK`) on the **first attempt**, immediately, with no delay and no retry needed — while systemd-networkd's own client continued to fail with the exact same `ENOMEDIUM` error on the exact same interface at the exact same point in the boot sequence. This is about as clean a confirmation as this class of bug allows: same kernel, same driver, same physical link, same moment in time, different client, different outcome.

**Fix shipped:** `01-eth0.network` (new, added to `sovereign-proof.rootfs-overlay`, overriding the upstream Raspberry Pi/Debian default identified in Sources and Environment above) sets `DHCP=no` and `RequiredForOnline=no` for `eth0`, handing IPv4 addressing entirely to a new `sovereign-eth0-dhclient.service` that runs `dhclient` directly. The service models `dhclient`'s own default fork-after-first-lease behavior correctly for systemd (`Type=oneshot` + `RemainAfterExit=yes`, so `network-online.target` genuinely waits for a real address rather than just a launched process), and restarts on failure. `isc-dhcp-client` was added as an `mmdebstrap` package to both `sovereign-data/image.yaml` and `sovereign-ab-data/image.yaml` — this bug is not layout-specific, so both the production single-root image and the RFC-0016 A/B image get the fix.

Hardware-verified on a genuine fresh reflash (not a warm reboot or a config reload on an already-running system): real DHCP lease acquired automatically (`inet 192.168.50.10/24 ... scope global dynamic eth0`), full routing table, working internet/DNS, and the appliance (Pi-hole) reporting healthy — all with zero manual intervention, replacing the earlier per-device static-IP workaround entirely.

## Unresolved Questions

- **Why** does systemd-networkd's DHCP client specifically fail while `dhclient` succeeds, on the same interface at the same moment? Not established — could be a difference in socket options, timing, or how each client probes interface readiness before sending. This remains genuinely unknown; the fix routes around the bug rather than explaining it.
- Is this reproducible on other qualification hardware, or specific to this one device/kernel build? Not tested — only one physical unit is available.
- Does disabling EEE (`ethtool --set-eee eth0 eee off`) independently resolve the systemd-networkd failure too, which would point at EEE renegotiation as the actual root cause? Not tested — `dhclient` resolved the practical problem first, so this line of investigation was left open rather than pursued further.

## Decision Impact

Fixed in `image-builder/sovereign/layer/sovereign-proof.rootfs-overlay` (`01-eth0.network`, `sovereign-eth0-dhclient.service`), applied to both `sovereign-data` and `sovereign-ab-data` image layers. No RFC or ADR was needed — this is an infrastructure-level reliability fix, not a design decision — but it's worth linking from RFC-0016's own qualification notes, since it was discovered during that work even though it's unrelated to base-OS updates specifically.
