# Raspberry Pi Image Release Checklist

**Status:** Draft  
**Applies to:** Phase 01 image candidates

## Release Identity

- [ ] Release version and channel assigned.
- [ ] Source revision recorded.
- [ ] Image-build-tool revision recorded.
- [ ] Raspberry Pi OS base release recorded.
- [ ] Docker, Compose, Nginx, and Avahi versions recorded.
- [ ] Pi-hole version, Linux ARM64 platform, and immutable digest recorded.
- [ ] Build environment recorded.
- [ ] Release notes and known limitations updated.

## Build Integrity

- [ ] Build starts from a clean, documented environment.
- [ ] Mutable `latest` references are absent.
- [ ] Build contains no developer credentials or local configuration.
- [ ] Package caches and temporary build files are removed.
- [ ] Machine ID is absent or prepared for first-boot regeneration.
- [ ] SSH host keys are absent and regenerated per device.
- [ ] Pi-hole administrator credential is not present in the image.
- [ ] Embedded container artifact matches the expected digest.
- [ ] Partition table and filesystems pass validation.
- [ ] Raw image size fits the advertised minimum storage.
- [ ] Dedicated `/data` partition exists and expands or is sized according to the documented policy.
- [ ] Pi-hole data, device secrets, backups, and update state resolve to `/data/sovereign`.
- [ ] Root filesystem replacement cannot silently become the authoritative location for persistent Pi-hole data.

## Static Security Inspection

- [ ] Image scanned for private keys, tokens, passwords, and shell history.
- [ ] Image scanned for build-host names, paths, users, and logs.
- [ ] Enabled systemd units reviewed.
- [ ] Listening-port expectations documented.
- [ ] Container runs without unnecessary capabilities or privileges.
- [ ] Pi-hole DHCP and NTP are disabled by default.
- [ ] Nginx configuration validation passes.
- [ ] `/admin/*` and `/api/*` are not routed to Pi-hole.

## Flash and First Boot

- [ ] Raspberry Pi Imager 2.0.11 or later is used and its exact version is recorded.
- [ ] The local `.rpi-imager-manifest` is generated from the published image.
- [ ] Imager presents Wi-Fi and SSH customization for the Sovereign OS entry.
- [ ] The compressed artifact is written using Raspberry Pi Imager with a test SSH public key and Wi-Fi configuration.
- [ ] Test uses the downloaded release artifact, not an intermediate image.
- [ ] Raspberry Pi 5 boots successfully.
- [ ] Root filesystem expands or otherwise exposes expected storage.
- [ ] Unique machine identity is generated.
- [ ] Unique SSH host keys are generated if SSH is enabled.
- [ ] The configured SSH key permits login and no shared default password exists.
- [ ] Wi-Fi connects without Ethernet using the settings supplied while flashing.
- [ ] `/boot/firmware/rpi-preseed.toml` is removed after it is consumed.
- [ ] Unique Pi-hole administrator credential is generated.
- [ ] Embedded Pi-hole artifact imports without internet access.
- [ ] First-boot completion is recorded only after health checks pass.
- [ ] First-boot duration is measured and documented.

## Service Verification

- [ ] Pi-hole container starts automatically.
- [ ] TCP port 53 answers from another local device.
- [ ] UDP port 53 answers from another local device.
- [ ] Default blocklists and upstream resolution work.
- [ ] Pi-hole data persists across reboot.
- [ ] Pi-hole data persists across container recreation.
- [ ] Pi-hole persistent mounts originate from the dedicated data partition.
- [ ] Nginx starts automatically.
- [ ] `sovereign.local` is advertised over mDNS.
- [ ] Direct-IP access works.
- [ ] Root URL redirects to `/dns/admin/`.
- [ ] Pi-hole UI works at `/dns/admin/`.
- [ ] Pi-hole API works at `/dns/api/`.
- [ ] Login, logout, assets, navigation, and redirects retain the prefix.
- [ ] Prefix traversal and escape tests fail safely.

## Failure and Recovery

- [ ] Power interruption during first boot is tested.
- [ ] First boot resumes without losing valid state.
- [ ] Container import failure is recoverable.
- [ ] Pi-hole health failure does not produce a false success marker.
- [ ] Nginx configuration failure is visible and diagnosable.
- [ ] mDNS failure leaves direct-IP access available.
- [ ] Port 53 conflict produces an actionable diagnostic.
- [ ] Reboot ordering is reliable across repeated tests.

## Resource and Stability

- [ ] Idle CPU and memory recorded.
- [ ] Representative DNS-load CPU and memory recorded.
- [ ] Storage usage recorded before and after first boot.
- [ ] Temperature and throttling behavior recorded.
- [ ] Defined continuous-run test passes.
- [ ] Log growth remains bounded.

## Published Artifacts

- [ ] `.img.zst` image published.
- [ ] SHA-256 checksum published.
- [ ] Release manifest published.
- [ ] Build provenance published at the agreed level.
- [ ] SBOM generated or an explicit deferral recorded.
- [ ] Installation and flashing instructions published.
- [ ] Stable-IP/router-DNS instructions published.
- [ ] Credential retrieval/reset procedure published.
- [ ] Recovery/reflash procedure published.
- [ ] Known limitations published.
- [ ] Published files are byte-for-byte identical to the hardware-qualified candidate.

## Approval

- [ ] Engineering verification complete.
- [ ] Security/privacy review complete.
- [ ] Documentation review complete.
- [ ] Project owner approves publication.
