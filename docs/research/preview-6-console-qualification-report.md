# Preview.6 Console Qualification Report

**Date:** 2026-07-22

**Hardware:** Raspberry Pi 5 Model B Rev 1.1, 16 GB RAM, 128 GB storage

**Candidate:** Sovereign OS `0.1.0-preview.6`

**Status:** Source fixes verified by live hotfix; rebuilt image required

## Baseline Results

- `sovereign.local` resolved to `192.168.50.10` with zero packet loss.
- Embedded release identity and `/opt/sovereign/current` correctly reported
  `0.1.0-preview.6`.
- Pi-hole, TCP/UDP DNS, `/dns/admin/`, DATA expansion, persistence mounts,
  update recovery audit, and protected update directories were healthy.
- `/console/` and `/console/health/` returned HTTP 500.
- `/api/v1/health` was reachable but falsely degraded storage and Pi-hole and
  omitted network interfaces.
- `sovereign-local-access.service` failed because its Console probe received
  HTTP 500.

## Root Causes

1. Exact Console locations used a file-valued Nginx `alias`; default index
   handling produced `index.htmlindex.html`.
2. The unprivileged health process attempted to read root-only readiness
   markers. Ongoing health should use bounded live outcomes instead.
3. The health service systemd sandbox omitted `AF_NETLINK`, which the fixed
   `ip -json` probe needs.
4. The operator CLI lived only in `/usr/sbin`, which is absent from some
   non-interactive user paths.
5. `sovereign-pihole.service` had no `ExecStop`; stopping the oneshot unit did
   not quiesce its container, invalidating the update-backup assumption.

## Hotfix Verification

The corresponding source fixes were temporarily installed on the candidate:

- `/console/`, `/console/health/`, CSS, and JavaScript returned HTTP 200.
- Health became `healthy` with DATA storage, Ethernet address, DNS, Pi-hole,
  local access, and update readiness all healthy.
- The health backend remained loopback-only on port 8090; Pi-hole HTTP remained
  loopback-only on port 8080.
- The local-access verification service completed successfully.
- An explicit Pi-hole stop changed the container to `exited` and closed port 53.
- Console stayed HTTP 200 and reported DNS and Pi-hole degraded.
- Starting the unit returned the container to `running healthy` without changing
  persistent mounts or credentials.

## Reboot and Persistence Verification

The hotfixed candidate was rebooted and tested again without further changes:

- The device returned at `sovereign.local` and retained `192.168.50.10` on
  Ethernet. Wi-Fi remained down, as expected for this Ethernet test.
- `/etc/sovereign-release` and `/opt/sovereign/current` still identified
  `0.1.0-preview.6`.
- The root, boot, and DATA partitions mounted from the expected SD-card
  partitions. The DATA partition retained approximately 113 GiB of usable
  capacity.
- Nginx, the Console health service, Pi-hole, local-access verification, and
  Docker were active with no failed systemd units.
- The update recovery audit exited successfully and `sovereign-update status`
  reported the installed version with an idle transaction state. The CLI was
  available at `/usr/bin/sovereign-update` to a normal SSH user.
- Pi-hole returned `Up (healthy)` and resolved external names over both UDP and
  TCP port 53.
- `/`, `/console/`, `/console/health/`, Console assets, `/api/v1/health`, and
  `/dns/admin/` behaved as designed. Reserved `/admin/` and `/api/` paths
  returned HTTP 404.
- The health API reported the overall appliance, DATA storage, DNS, update
  subsystem, Pi-hole, and local access as healthy.
- Ports 22, 53, and 80 were reachable from the LAN. Internal Pi-hole and health
  backends on ports 8080 and 8090 remained loopback-only.
- The boot-generated local-access marker contained pass results for Nginx,
  redirects, Console, health API, Pi-hole UI, reserved paths, and path-escape
  protection.
- The SSH key installed during qualification remained usable after reboot.
  Secret and update-state directories remained mode `0700`, with individual
  credentials and locks mode `0600`.

One early HTTP probe was refused after the host and DNS had already become
reachable. The Console recovered without intervention and was healthy by 82
seconds of uptime. A future Console should expose clearer boot progress, and
clients and test tooling should treat network reachability separately from
application readiness.

## Conclusion

The Console design, degraded-state behavior, and reboot recovery are valid after
the source fixes. Preview.6 itself is not qualified because the fixes were
installed after flashing. The next immutable image must repeat healthy,
degraded, reboot, and local-access checks before serving as the base for
appliance-update testing.
