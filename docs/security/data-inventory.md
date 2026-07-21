# Phase 01 Data Inventory

**Status:** Draft  
**Version:** 0.2

| Data | Source | Purpose | Location | Transmitted | Sensitivity | Rule |
| --- | --- | --- | --- | --- | --- | --- |
| Base appliance configuration | Image/project owner | Runtime defaults | `/etc/sovereign/` | No | Low/Medium | No device secrets |
| Machine identity | First boot | Unique host identity | Base-OS locations | mDNS/network protocols as required | Medium | Must not originate from build host |
| SSH host keys | First boot | SSH server identity if enabled | `/etc/ssh/` | During SSH | High | Unique per device; absent from image |
| Preview bootstrap password hash | Release image | First headless login | `/etc/shadow` | SSH authentication on LAN | High | Public temporary credential; expired before release; prohibited in production |
| Pi-hole admin password | First boot | UI/API authentication | `/data/sovereign/secrets/` | To local Pi-hole login/API | High | Root-owned; never in image, YAML, or logs |
| Pi-hole configuration | Pi-hole/user | DNS and UI behavior | Persistent Pi-hole volume | No by default | Medium/High | Survives container recreation |
| DNS query data | LAN clients/Pi-hole | Resolution, blocking, statistics | Persistent Pi-hole volume/logs | To configured upstream DNS as required | High | Household metadata; document retention/privacy defaults |
| Client identifiers | Pi-hole | Statistics and troubleshooting | Persistent Pi-hole data | No by default | High | Avoid duplicating in Nginx/system logs |
| Upstream DNS requests | Pi-hole | Resolve allowed domains | Selected upstream resolver | Internet | High | Default provider and privacy behavior documented |
| Pi-hole OCI artifact | Release build | Offline first boot | `/opt/sovereign/bootstrap/` until import | No | Low/Integrity-critical | Pinned and verified by digest |
| Container runtime state | Docker | Run Pi-hole | `/var/lib/docker/` | Registry only during explicit future updates | Medium | Not a backup substitute for Pi-hole data |
| First-boot state | Initializer | Idempotency and recovery | `/data/sovereign/update-state/` | No | Medium | Atomic, health-gated completion |
| Nginx access/error logs | Nginx | Diagnostics | Host logs | No by default | Medium | Bounded; avoid credentials/query payloads |
| Pi-hole logs | Pi-hole | DNS and service diagnostics | Persistent volume | No by default | High | Rotation and privacy defaults documented |
| Avahi service metadata | Host | Local discovery | Runtime/config | Local multicast | Low | Advertise service identity only |
| Build manifest | Build pipeline | Provenance | Release artifact | Published | Low | Must not include build credentials or sensitive paths |
| Diagnostic bundle | User-initiated future tool | Support | Generated on request | Only when user shares it | High | Contents previewed and redacted before sharing |

## Required Decisions

- Exact persistent paths and ownership
- Initial password delivery and reset mechanism
- Production replacement for the preview bootstrap credential
- Pi-hole privacy level and query retention default
- Nginx and Pi-hole log retention
- Diagnostic bundle contents
- Backup, restore, and reflash semantics
- Default upstream DNS provider
- Treatment of IPv6 client and query data

## Image Sanitization Rule

The final exported image must be checked for:

- machine IDs;
- SSH host private keys;
- Pi-hole passwords;
- Docker registry credentials;
- build-system tokens;
- Wi-Fi credentials;
- shell history;
- build-host paths and usernames;
- DNS query history;
- package-manager and installation logs containing sensitive build context.
