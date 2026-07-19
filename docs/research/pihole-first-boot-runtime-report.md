# Pi-hole First-Boot Runtime Report

Status: **Runtime configuration and isolated execution passed; Pi 5 boot and credential delivery pending**
Build date: 2026-07-19

## Outcome

Sovereign OS now configures and starts the pinned Pi-hole container after the
DATA filesystem, Docker runtime, embedded-artifact verification, and image
import are ready. Configuration, Pi-hole data, the generated administrator
secret, and the completion marker are all persisted under `/data`.

The implementation follows Pi-hole v6's documented `FTLCONF_*` configuration
and `WEBPASSWORD_FILE` Compose-secret mechanisms. Pi-hole's documentation also
states that the proxy prefix must be stripped before forwarding to its backend;
therefore the container advertises `/dns` in generated links while its
loopback-only backend health check uses `/admin/`.

Sources:

- [Official Pi-hole Docker configuration](https://docs.pi-hole.net/docker/configuration/)
- [Official Pi-hole webserver prefix configuration](https://docs.pi-hole.net/ftldns/configfile/#prefix)

## Persistent Layout

```text
/data/sovereign/
├── apps/
│   └── pihole/
│       ├── compose.yaml
│       └── etc-pihole/
├── secrets/
│   └── pihole-admin-password
└── pihole-ready
```

The administrator password is generated from 18 bytes of kernel randomness,
encoded as 36 hexadecimal characters, created with a restrictive umask, and
stored with mode `0600`. Compose mounts it read-only at runtime rather than
placing it in the Compose environment or Docker image.

## Runtime Defaults

| Setting | Value |
|---|---|
| Image | single-source immutable Pi-hole ARM64 digest |
| DNS | host TCP and UDP port 53 |
| HTTP backend | `127.0.0.1:8080` only |
| External prefix metadata | `/dns` |
| Persistent Pi-hole directory | `/data/sovereign/apps/pihole/etc-pihole` |
| Upstream resolvers | Cloudflare `1.1.1.1;1.0.0.1` |
| DHCP | disabled |
| Pi-hole NTP server and synchronization | disabled |
| Restart policy | `unless-stopped` |
| Added capabilities | none |
| Dropped capabilities | `NET_RAW` |

The host's systemd-resolved stub listener is disabled to release port 53. The
host resolver uses `/run/systemd/resolve/resolv.conf`, avoiding a dependency on
Pi-hole for the appliance's own upstream name resolution and preventing a
startup loop.

## Idempotent First Boot

`sovereign-pihole.service` performs the following sequence:

1. Creates persistent application and secret directories with fixed modes.
2. Generates the administrator password only when no non-empty secret exists.
3. Materializes Compose from the immutable pin and appliance template.
4. Runs `docker compose up --detach --no-build --pull never`.
5. Waits up to 180 seconds for Pi-hole's built-in DNS health check.
6. Queries `pi.hole` against host port 53.
7. Checks the loopback-only HTTP backend.
8. Atomically records image identity and DNS/HTTP success.

The unit restarts on failure, while reruns preserve both the password and
Pi-hole data.

## Verification

An isolated ARM64 runtime test used the exact pinned image and production
settings on non-conflicting high loopback ports:

```text
health=healthy
DNS pi.hole -> 127.0.0.1
backend /admin/ -> HTTP 302
webserver.paths.prefix -> /dns
dhcp.active -> false
ntp.ipv4.active -> false
CapDrop -> CAP_NET_RAW
```

The complete native ARM64 appliance build passed. Its root filesystem contains
the expected first-boot script, Compose template, `bind9-dnsutils`, resolved
configuration, and enabled systemd unit.

| Artifact | Result |
|---|---|
| Flashable image | `build/sovereign-image/deploy/sovereign-proof.img.zst` |
| Compressed size | 348 MiB |
| SHA-256 | `8af8daacb5d3ef88c90f3e7d00ca4d10ca5696f54bcb845e14157b05e0102fbe` |

## Remaining Qualification and Product Gap

The generated administrator credential currently has no shell-free delivery
flow. It is safely persisted, but the POC user cannot retrieve it through the
browser yet. This is deliberately not solved by publishing the secret on the
unencrypted boot partition or weakening Pi-hole authentication.

The next milestone must select and implement a safe delivery mechanism while
adding Nginx `/dns/*` routing and Avahi `sovereign.local` discovery. Physical
Pi 5 testing must additionally confirm port ownership, first-boot recovery,
DNS access from another LAN client, container recreation, and persistence
across reboot.
