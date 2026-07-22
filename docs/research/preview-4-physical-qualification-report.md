# Preview 0.4 Physical Qualification Report

**Status:** Concluded; release blockers found

**Date:** 2026-07-22

**Target:** Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM, 128 GB microSD

## Outcome

Preview 0.4 proves the core appliance flow on physical hardware but is not a
release-qualified image. Raspberry Pi OS, Docker, the embedded pinned Pi-hole
ARM64 image, DNS, Nginx routing, Avahi discovery, bootstrap access, and
persistent container state all operate on the target Pi.

Qualification found two release blockers and several major correctness issues.
The source fixes described below require a newly built and freshly flashed image
before they can be marked physically verified.

## Passed Evidence

- Raspberry Pi 5 ARM64 boot and unique device/SSH identity
- Ethernet DHCP, `sovereign.local`, direct-IP access, and SSH onboarding
- Embedded Pi-hole artifact verification and offline Docker import
- Healthy Pi-hole container using the pinned ARM64 digest
- UDP and TCP DNS from the Pi and another LAN device
- Root redirect and `/dns/admin/` login page
- UI assets remain beneath `/dns/`
- Root `/admin/*`, root `/api/*`, and prefix traversal return 404
- Only SSH, DNS, and HTTP application ports are exposed to the LAN
- Pi-hole restart, container recreation, and normal reboot recovery
- Device credential file remains byte-identical across recreation and reboot
- 500 parallelized DNS queries complete with zero failures
- Approximately 356-429 MiB host memory use while idle or after load
- 53.8-56.0 degrees Celsius and `throttled=0x0`
- Temporary qualification privilege removed after testing

## Release Blockers

### DATA Did Not Expand

The 128 GB device retained a 512 MiB DATA partition while more than 100 GB
remained unused. `/data` was already 56 percent full after first boot.

The `expand-to-fit` provision map is not applied when the release is written as
a normal raw image. The source now installs `growpart`, runs a dedicated
`sovereign-data-expand.service`, expands the final partition and ext4 filesystem
online, and gates containerd, Docker, and appliance initialization on success.

### Stored Pi-hole Credential Was Rejected

The generated password file existed with correct root ownership and mode 0600,
but Pi-hole rejected that password through `/api/auth`.

The Compose template supplied the mounted path as `WEBPASSWORD_FILE`. Pi-hole's
Compose-secret contract expects the secret name. The source now uses
`WEBPASSWORD_FILE: pihole_webpasswd` and requires a successful authenticated API
request before writing `pihole-ready`.

## Major Findings and Source Corrections

### Network Readiness Delay

Unconfigured `wlan0` remained in `configuring`, causing
`systemd-networkd-wait-online` to fail after approximately two minutes even
though Ethernet was routable. The product WLAN network file now sets
`RequiredForOnline=no`; Wi-Fi-only behavior still requires physical testing with
a configured IWD profile.

### Local-Access Verifier Retry Loop

The verifier required a relative Location header, while Nginx returned a valid
same-host absolute redirect. It retried every ten seconds and generated
continuous failure logs. The verifier now compares curl's normalized redirect
URL, tests `/dns/`, and the unit has a bounded start limit.

### `/dns/` Returned 403

`/dns` redirected correctly, but `/dns/` was proxied to Pi-hole's root and
returned 403. Nginx now defines an exact `/dns/` redirect to `/dns/admin/`.

## Deferred Findings

- `pi.hole` returned the Docker bridge address rather than the LAN address.
- TCP DNS initially attempted an unreachable link-local IPv6 address before
  falling back to IPv4.
- Docker resource reporting returned `0 B / 0 B` for the container on this host.
- Deliberate power interruption, corrupt artifact, port conflict, invalid Nginx
  configuration, and extended soak tests were not performed.

These do not replace the fresh-image acceptance tests for the blockers above.

## Required Requalification

The next image must demonstrate:

1. DATA grows to the documented share of 32, 64, and 128 GB media.
2. The generated Pi-hole password authenticates before first-boot completion.
3. Ethernet boot does not wait for unconfigured Wi-Fi.
4. `systemctl --failed` is empty after boot.
5. `/`, `/dns`, and `/dns/` redirect to `/dns/admin/`.
6. `sovereign-local-access.service` completes once without restart churn.
7. Credential, Pi-hole state, DNS, and HTTP survive recreation and reboot.
