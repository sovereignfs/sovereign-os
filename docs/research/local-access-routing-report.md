# Local Access Routing Implementation Report

**Status:** Implemented and assembled; hardware verification pending

**Date:** 2026-07-19

## Outcome

The Sovereign image definition now provides a single LAN HTTP entry point:

- `http://sovereign.local/` redirects to `/dns/admin/`;
- `http://sovereign.local/dns/admin/` proxies to Pi-hole;
- `/dns/api/*` uses the same proxy namespace;
- `/admin/*` and `/api/*` return `404` and remain available for future Sovereign services;
- the Pi-hole backend remains bound only to `127.0.0.1:8080`;
- the same behavior is available through the device IP address.

Nginx's trailing-slash `proxy_pass` form replaces the normalized matching `/dns/` location prefix with `/`, so Pi-hole receives `/admin/` or `/api/`. Pi-hole's configured `/dns` prefix remains responsible for external links and redirects.

## Service Ordering and Health

Nginx requires the Pi-hole first-boot service and uses the package's configuration validation before startup. A Sovereign verification unit then checks:

- Nginx configuration validity;
- the root redirect;
- the proxied Pi-hole UI;
- isolation of `/admin/` and `/api/`;
- rejection of a normalized `/dns/../admin/` prefix escape.

Only a successful run creates `/data/sovereign/local-access-ready`. The unit wants Avahi but does not require it, preserving direct-IP access when mDNS is unavailable.

## Discovery

Avahi advertises `_http._tcp` on port 80 with a `/dns/admin/` path hint. The configured image hostname supplies `sovereign.local`. Client and duplicate-hostname behavior still require real-network qualification.

## Initial Credential Delivery

For the POC, a systemd oneshot displays the generated Pi-hole password and both access URLs on `/dev/tty1` after local HTTP verification succeeds. Output is sent directly to the attached physical console rather than the journal. The password continues to live only in the root-readable file on the persistent DATA partition.

This is intentionally a physical-access mechanism. A headless user needs a temporarily attached display to obtain the initial password; a future claim or provisioning flow can replace it without changing Pi-hole's stored credential model.

## Remaining Verification

- boot the exported artifact on a Raspberry Pi 5;
- run UI, asset, redirect, login, logout, and API prefix tests from another device;
- verify mDNS across the supported client matrix;
- inspect listening sockets and confirm Pi-hole HTTP is not exposed directly;
- confirm the password is visible on tty1 and absent from the journal;
- repeat tests after reboot and with Avahi stopped.

## Build Evidence

The ARM64 engineering build completed successfully and exported the compressed flash image at `build/sovereign-image/deploy/sovereign-proof.img.zst` (ignored by Git).

- compressed size: 367,700,590 bytes (351 MiB);
- SHA-256: `d16e9ebb9f813a45aa62965899b4a2ff9ec1235b384780c261fa8015f88645f1`;
- Nginx: `1.26.3-3+deb13u7`;
- Avahi: `0.8-16`;
- `libnss-mdns`: `0.15.1-4+b1`.

The assembled files were compared with their source definitions, including executable modes on both Sovereign helper scripts. The Nginx configuration also passed `nginx -t` using an isolated ARM64 Nginx 1.26.3 runtime. This remains an engineering build on the Apple Silicon Docker adapter, not a qualified release build.

## Sources

- [Nginx `proxy_pass` URI replacement behavior](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)
- [Pi-hole webserver path-prefix configuration](https://docs.pi-hole.net/ftldns/configfile/#prefix)
- [Avahi DNS-SD service definitions](https://avahi.org/doxygen/html/lookup_8h.html)
