# Local Network Discovery

**Status:** Concluded for the Phase 01 POC

**Date:** 2026-07-19

## Question

How should a user reliably find the Phase 01 Pi-hole appliance from common phones and computers on a home network?

## Decision

Use two independent access methods:

1. Advertise `sovereign.local` with Avahi/mDNS as the convenient default.
2. Keep the appliance reachable at its DHCP-assigned IP address as the required fallback.

Avahi publishes an `_http._tcp` service on port 80 with `path=/dns/admin/`. The image hostname is `sovereign`, which produces the expected `sovereign.local` mDNS name. The appliance does not create or depend on a unicast `.local` DNS zone.

## Why

mDNS gives the POC a memorable zero-configuration address without requiring router integration. It is not universally reliable: client support, Wi-Fi isolation, VLANs, multicast filtering, and duplicate hostnames can prevent resolution. Direct-IP access uses the same Nginx routes and remains available even if Avahi fails.

Router-provided DNS and Pi-hole local DNS are not appropriate bootstrap dependencies. Both require additional network configuration, and Pi-hole cannot be the only mechanism used to discover itself before clients have adopted it as their DNS resolver.

## Conflict Behavior

Avahi may rename a host when another `sovereign` name already exists on the link. That makes the friendly hostname unpredictable, but it does not affect direct-IP access or DNS service. Duplicate-name behavior must be recorded during physical-device testing and documented as a POC limitation.

## Validation Matrix

The exported image still requires physical testing from representative clients:

- macOS or iOS;
- Linux with mDNS enabled;
- Windows 11;
- Android on the same, non-isolated Wi-Fi network;
- direct IPv4 access with Avahi stopped;
- duplicate `sovereign` hostname behavior.

## Sources

- [Avahi lookup API: standard `.local` domain and DNS-SD service types](https://avahi.org/doxygen/html/lookup_8h.html)
- [RFC 6762: Multicast DNS](https://www.rfc-editor.org/rfc/rfc6762)

## Decision Informed

[RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md), local addressing implementation, and the physical Pi 5 qualification checklist.
