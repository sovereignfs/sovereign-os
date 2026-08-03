# Research: systemd-networkd DHCP client fails with ENOMEDIUM on eth0 despite a stable carrier

**Status:** Concluded (root cause isolated; general fix unresolved)
**Author:** Claude (with kasunben), during RFC-0016 hardware qualification
**Started:** 2026-08-03
**Concluded:** 2026-08-03
**Decision informed:** none yet — flagged as a real product reliability gap, not yet triaged into a roadmap item

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

## Recommendation

Do not attempt a quick one-line fix in `image-builder` yet — the `IPv6AcceptRA=no` test proved the obvious fix is insufficient for the case that actually matters (real devices using DHCP on arbitrary networks). This needs a dedicated investigation pass (likely: reproduce reliably enough to bisect kernel/systemd versions, test a startup-delay workaround, or check upstream Raspberry Pi / systemd bug trackers for this exact `macb` + `ENOMEDIUM` signature) before proposing a change to the shipped `01-eth0.network` config. Track this as its own piece of work, separate from RFC-0016.

## Unresolved Questions

- Does a fixed startup delay (e.g., `systemd-networkd-wait-online` tuning, or a custom `ExecStartPre` sleep) reliably avoid the race, or does the window vary enough that no fixed delay is fully safe?
- Is this reproducible on other qualification hardware, or specific to this one device/kernel build?
- Would installing and using a different DHCP client sidestep the bug entirely (suggesting it's specific to systemd-networkd's implementation), or does the race exist at a lower level that any client would hit?

## Decision Impact

None yet. This is a flagged finding, not yet triaged into an RFC, ADR, or ROADMAP item. It represents a real reliability gap worth prioritizing before this image ships more broadly, since a device that boots without working DHCP would be unreachable for any user who can't fall back to IPv6-link-local SSH the way this session did.
