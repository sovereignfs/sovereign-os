# Phase 01 Image Threat Model

**Status:** Draft  
**Version:** 0.2  
**Scope:** Flashable Docker-based Pi-hole appliance image

## Security Goals

- Publish an image free of build-machine identity and secrets.
- Give every flashed device unique identity and credentials.
- Expose only the network services required for DNS and local administration.
- Prevent Pi-hole from occupying future Sovereign `/admin` and `/api` namespaces.
- Keep Pi-hole data and credentials on user-owned storage.
- Make interrupted initialization recoverable.
- Make release inputs and artifacts verifiable.

## Protected Assets

- Raspberry Pi host and boot integrity
- Pi-hole administrator credential
- Pi-hole configuration, query data, client identities, and statistics
- Docker daemon and host filesystem
- Persistent application data
- Image build and release integrity
- Future Sovereign route namespaces

## Actors and Boundaries

- Authorized household administrator
- Other devices and users on the local network
- Internet hosts contacted for upstream DNS and later updates
- Base-OS and package repositories
- Container registry and Pi-hole release publishers
- Compromised dependency or build environment
- Physical holder of the Raspberry Pi or storage device

The local network reduces exposure but is not fully trusted. Physical compromise and hostile public internet exposure are outside Phase 01 protection claims.

## Threats and Controls

### T-01: Shared or Leaked Image Credentials

**Threat:** Every flashed device inherits the same password, SSH keys, machine ID, token, or build-host secret.  
**Controls:** Generate identity and credentials on first boot; sanitize the final filesystem; scan the exported image; prohibit credentials in build configuration and Compose YAML.  
**Verification:** Mount and scan the exact compressed release artifact after decompression.

### T-02: Malicious or Mutable Build Input

**Threat:** A changed base image, package, script, or `latest` container silently alters a release.  
**Controls:** Pin source revisions and Pi-hole digest; record base-OS and package inputs; publish checksums and provenance; review dependency sources.  
**Verification:** Compare manifest inputs and verify the embedded OCI digest.

### T-03: Docker Daemon or Container Escape

**Threat:** Compromise of Pi-hole gains unnecessary host authority.  
**Controls:** No Docker socket mount; no privileged mode; no unnecessary capabilities; limited bind mounts; patched runtime; host directories with restrictive ownership.  
**Verification:** Inspect effective container configuration and mount/capability sets.

### T-04: Unintended Network Exposure

**Threat:** Docker or host services publish administrative or internal ports beyond the intended LAN boundary.  
**Controls:** Document listener ownership; Pi-hole web backend bound to loopback; only DNS and Nginx intentionally exposed; firewall and socket inspection.  
**Verification:** Scan the target from another local device and inspect host/container listeners.

### T-05: Unauthenticated Pi-hole Administration

**Threat:** Another local device obtains administrative access.  
**Controls:** Unique strong password; no empty password; secure password delivery; no password in logs or unauthenticated endpoints.  
**Verification:** Attempt access without credentials and inspect all delivery/log paths.

### T-06: Route Prefix Escape

**Threat:** Ambiguous paths, encoded traversal, or proxy behavior sends `/admin` or `/api` traffic to Pi-hole or escapes `/dns`.  
**Controls:** Explicit Nginx locations; normalized paths; Pi-hole prefix setting; reject ambiguous encodings; regression tests.  
**Verification:** Test normal, encoded, doubled-slash, and traversal-shaped requests.

### T-07: DNS Service Abuse

**Threat:** Pi-hole becomes an open resolver or answers on unintended interfaces.  
**Controls:** Local-network listening policy; no router port forwarding; documented firewall; verify IPv4 and IPv6 behavior.  
**Verification:** Inspect bindings and test from permitted and non-permitted network positions where available.

### T-08: Sensitive DNS Data Disclosure

**Threat:** Query history or client identity appears in host logs, support artifacts, or unintended routes.  
**Controls:** Pi-hole data stays in its persistent directory; minimize proxy logs; document query logging/privacy defaults; inspect diagnostic output.  
**Verification:** Generate identifiable test queries and search normal logs and release artifacts.

### T-09: First-Boot Corruption

**Threat:** Power loss leaves partial secrets, imported images, invalid configuration, or a false completion state.  
**Controls:** Idempotent steps; atomic writes; restrictive permissions before content; health-gated completion; recoverable embedded artifact.  
**Verification:** Interrupt power or service execution at defined steps and resume.

### T-10: DHCP Disruption

**Threat:** Pi-hole DHCP competes with the router and disrupts the household network.  
**Controls:** DHCP disabled; port 67 unpublished; no `NET_ADMIN` solely for DHCP.  
**Verification:** Inspect Pi-hole configuration, Compose ports, and effective capabilities.

### T-11: Unsafe Update or Rollback

**Threat:** Incompatible Pi-hole or container changes corrupt persistent data.  
**Controls:** No unattended `latest` pulls; explicit pinned releases; backup and migration testing before update; compatibility notes.  
**Verification:** Test updates on copied data before publishing an update path.

## Required Security Tests Before Release

- Final image identity and secret scan
- SBOM or documented Phase 01 deferral
- Container digest verification
- Container privilege, mount, and capability inspection
- Host and remote port scans
- `/dns/*` path-boundary regression tests
- Authentication and password reset tests
- First-boot interruption tests
- IPv4 and IPv6 exposure review
- Log and diagnostic data review

## Known Phase 01 Limitations

- HTTP is not confidential on the local network.
- mDNS is discovery, not authentication.
- The image is not designed for public internet exposure.
- Anyone with physical storage access may read unencrypted Pi-hole data and secrets.
- Automatic security update and rollback infrastructure is not yet implemented.
- Router security and configuration remain outside the image's control.

