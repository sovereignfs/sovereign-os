# Versioned Appliance Release Design

**Status:** Implemented; Raspberry Pi qualification pending

**Related milestone:** [Appliance Update Foundation](../roadmap/01-1-update-foundation.md)

## Objective

Extend the qualified Pi-hole-only update transaction so one signed release can
also update Sovereign-owned Console, routing, Compose, lifecycle, and health
files without reflashing the base OS or writing into persistent application
data.

The atomic `/opt/sovereign/current` pointer remains the only appliance
activation boundary.

## Ownership Boundary

The flashed base owns components that must remain available while an appliance
release is being authenticated or recovered:

- `/usr/sbin/sovereign-update` and its `/usr/bin` wrapper;
- the update-recovery, storage, provisioning, artifact-import, and stable
  service units;
- Docker, containerd, Nginx, SSH, networking, and other OS packages;
- DATA partition discovery and expansion; and
- the embedded recovery OCI artifact.

An appliance release owns files that may change together behind the active
pointer:

```text
/opt/sovereign/releases/<version>/
├── sovereign-release
├── pihole-image.env
└── appliance/
    ├── bin/
    │   ├── console-health
    │   ├── start-pihole
    │   ├── stop-pihole
    │   ├── verify-local-access
    │   └── verify-update-health
    ├── console/
    │   ├── index.html
    │   └── assets/
    │       ├── console.css
    │       └── console.js
    ├── nginx/
    │   └── sovereign.conf
    └── pihole/
        └── compose.yaml.in
```

Credentials, Pi-hole configuration/database state, generated Compose content,
backups, transaction journals, and household data remain under
`/data/sovereign`. They are never release payload files.

## Stable Dispatch

Stable base-image systemd units execute versioned programs through
`/opt/sovereign/current/appliance/bin/`. Nginx's stable enabled-site file
contains only an include of
`/opt/sovereign/current/appliance/nginx/sovereign.conf`. The versioned Nginx
site serves Console assets from the active release.

Long-running services do not change merely because a symlink changes. Update
activation therefore stops the affected services, atomically switches
`current`, and starts them in dependency order. Rollback performs the same
sequence after restoring the previous pointer.

The stable units and updater are deliberately not self-updated in this slice.
Changing that recovery substrate requires a separate bootstrap/self-update
design.

## Initial Image

Image construction installs the same canonical appliance tree used by update
packaging into the image's versioned release directory. First boot verifies the
required tree and creates `current` only when it is absent. It does not rebuild
the release from mutable copies under `/usr` or `/etc`.

This prevents clean-image and update artifacts from drifting into two different
appliance layouts.

## Target Validation

Staging remains hostile until every declared file passes the closed bundle
manifest. Before any service interruption, the updater additionally requires:

- the complete appliance allowlist and no unknown file types;
- executable mode only for the five declared programs;
- Python compilation of `console-health`;
- POSIX shell syntax checks for lifecycle and health scripts;
- successful rendering and `docker compose config` validation of the target
  Pi-hole template using the signed image digest;
- target Nginx syntax validation through a temporary top-level configuration
  that directly includes the staged target site;
- required local Console asset references and no remote asset URLs; and
- release identity, channel, device, data schema, and Pi-hole metadata matching
  the signed outer manifest.

Validation reads target files but does not switch the active release, stop a
service, write persistent configuration, or import an OCI image.

## Activation Sequence

After validation and OCI digest verification:

```text
record activation metadata
→ state = activating
→ stop local-access, Nginx, Console, and Pi-hole
→ atomically switch /opt/sovereign/current
→ start Pi-hole, Console, and Nginx
→ restart local-access verification
→ state = validating
→ run the active release's complete health gate
→ state = committed
```

The health gate covers the container digest/health, TCP and UDP DNS, Pi-hole
HTTP, Nginx syntax, Console/API routing, reserved namespaces, and DATA mount.

If any activation or validation step fails, the updater stops the affected
services, restores the previous pointer, starts the previous release in the
same order, and records `rolled_back` only after that release passes its own
health gate. Otherwise it records `recovery_required`.

## Reboot Recovery

The stable boot recovery unit runs before Pi-hole. An interruption at
`activating`, `validating`, or `rolling_back` restores the previous pointer from
durable activation metadata. Normal systemd startup then launches all affected
services through that restored release.

Recovery never executes a partially staged target program and never infers a
commit.

## Acceptance Evidence

Automated tests must prove:

- clean-image and update packaging contain the same appliance allowlist;
- missing, extra, malformed, unsafe-mode, invalid Nginx, invalid Compose, and
  externally hosted Console payloads are rejected before activation;
- a successful transaction changes an observable versioned Console asset and
  commits the target;
- activation failure restores the prior appliance files and Pi-hole release;
- deterministic interruptions restore the prior pointer on boot; and
- persistent DATA and credentials are never packaged or replaced.

Physical Raspberry Pi qualification is required after implementation. It must
use a clean base image containing the stable dispatch boundary and a separate
target update artifact containing an observable appliance-file change.

The Console footer contains a release-version placeholder rendered independently
by full-image and update packaging. This gives qualification a static asset to
observe before activation, after activation, after rollback, and after reboot.
