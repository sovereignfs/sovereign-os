# Embedded OCI Artifact Proof Report

Status: **Embedding and ARM64 runtime compatibility passed; on-device import pending Docker milestone**  
Build date: 2026-07-19

## Outcome

The Sovereign image build now creates and embeds a deterministic OCI Image
Layout archive containing a small static ARM64 executable. The exact archive
extracted from the completed appliance build was checksum-verified, imported
into Docker Desktop's ARM64 Linux runtime, inspected as `linux/arm64`, and run
successfully.

This proves the artifact creation, image embedding, digest, OCI import, and
ARM64 execution mechanisms without introducing Pi-hole or a container runtime
into the appliance image prematurely.

## Embedded Artifact

| Property | Result |
|---|---|
| Reference annotation | `sovereign/oci-proof:arm64` |
| Format | OCI Image Layout 1.0.0 archive |
| Platform | `linux/arm64` |
| Archive size | 614,400 bytes |
| Archive SHA-256 | `351bf05144e685b64f6c394dd145b6f7bc94d7aaca1bc3fe678875112fd4c431` |
| Manifest digest | `sha256:460eeda655ef03c6ce827a556ca81fcf64b67811d0d398c758d7e947da2755a1` |
| Payload | statically linked ARM64 executable |
| Expected output | `Sovereign ARM64 OCI artifact proof` |

Inside the appliance root filesystem, the archive and its verification records
live under:

```text
/usr/lib/sovereign/artifacts/
```

Local ignored evidence is exported to:

```text
build/sovereign-image/evidence/oci/
```

## Determinism

The generator fixes ownership, modes, file ordering, timestamps, JSON encoding,
and tar format. Two equivalent generator runs produce byte-identical archives.
The static executable is compiled for ARM64 during the native ARM64 image build
with the linker build ID disabled.

The OCI archive contains:

- `oci-layout`;
- `index.json` with an explicit `linux/arm64` platform;
- a canonical image manifest;
- a canonical image configuration;
- one uncompressed layer containing `/usr/bin/sovereign-oci-proof`.

## First-Boot Verification

The image installs and enables `sovereign-oci-proof.service`. After `/data` is
mounted, it:

1. verifies the embedded archive SHA-256;
2. verifies the OCI layout, index, and recorded manifest blob exist;
3. records the archive and manifest digests in
   `/data/sovereign/oci-proof-ready`.

Physical execution of this unit remains part of the Pi 5 test checklist.

## Runtime Import Verification

The exact exported archive was loaded into the local ARM64 Docker runtime. The
runtime reported `linux/arm64`, assigned the expected immutable image ID, and
executed the payload successfully:

```text
Sovereign ARM64 OCI artifact proof
```

Docker Desktop displayed duplicate rows for the same immutable image ID after
repeated loads, but the imported content and ID were identical.

## Acceptance Boundary

The proof plan originally combined embedding with first-boot import. The
accepted roadmap intentionally puts OCI embedding before Docker installation.
Installing Podman only for this proof would create a throwaway production
dependency, so the acceptance is split:

- completed here: deterministic creation, embedding, checksum verification,
  Docker import compatibility, and ARM64 execution;
- next Docker milestone: install the selected runtime in the appliance, import
  this exact archive on first boot, verify its runtime digest, and persist the
  result under `/data`.

The test archive should be replaced with the pinned Pi-hole OCI artifact only
after on-device runtime import passes.

