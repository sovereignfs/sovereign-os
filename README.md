# Sovereign OS

Sovereign OS is a local-first, open-source operating system for Raspberry Pi—a foundation for private, self-hosted services and user-owned computing.

The project aims to make personal infrastructure approachable without giving up ownership, privacy, interoperability, or the ability to operate locally. It brings proven open-source services together behind a coherent installation, runtime, update, and recovery experience.

## Principles

- **Local first:** Core capabilities should continue to work without a mandatory cloud dependency.
- **User owned:** Users control their hardware, data, configuration, and service lifecycle.
- **Privacy preserving:** Data collection and external communication should be explicit, minimal, and documented.
- **Open and auditable:** Source, build inputs, artifacts, and important technical decisions should be inspectable.
- **Modular:** Services should remain replaceable and independently maintainable behind stable platform boundaries.
- **Recoverable:** Installation and updates should have clear backup, rollback, and recovery paths.

## Current Status

Sovereign OS is in early development and is not yet a production release.

The current phase is proving the appliance foundation on Raspberry Pi 5: a reproducible ARM64 image, persistent user data, containerized services, local network discovery, namespaced HTTP routing, first-boot initialization, and a versioned release-candidate pipeline. Pi-hole is the first integrated service used to validate that foundation; it is not the limit of the project.

Current engineering images still require physical Raspberry Pi 5 qualification before they should be treated as releases.

## Preview First Login

Preview images built after the bootstrap-access change support a headless first
login over a trusted Ethernet network:

```text
Address:  sovereign.local
Username: sovereign
Password: sovereign
```

The password is public and temporary. SSH requires it to be replaced before
opening the first shell. Do not connect a preview device directly to the
internet or forward its SSH port from a router.

```bash
ssh sovereign@sovereign.local
```

Pi-hole is available over HTTP on the trusted local network at
`http://sovereign.local/dns/admin/`. HTTPS with automatic browser trust is not
part of the POC because public certificate authorities cannot issue for the
private `.local` name.

See the [first-login and network setup guide](docs/operations/first-login-and-network-setup.md)
for the mandatory password change, Pi-hole credentials, SSH-key hardening,
Wi-Fi setup, and recovery procedure.

## Repository

```text
.github/workflows/   validation and ARM64 image-build automation
docs/                product, architecture, research, security, and operations
image-builder/       pinned Raspberry Pi image definition and appliance layer
scripts/             local build and release tooling
tests/               automated tooling tests
```

Start with:

- [Project concept](CONCEPT.md)
- [Public roadmap](ROADMAP.md)
- [Documentation index](docs/README.md)
- [Phase 01 plan](docs/roadmap/01-preview-poc.md)
- [System architecture](docs/architecture/system-overview.md)
- [Image build and release process](docs/operations/image-build-and-release.md)

## Building

The image builder currently targets Raspberry Pi 5 and ARM64. The supported release environment still requires qualification; Docker Desktop on Apple Silicon is used only as an engineering adapter.

From the repository root:

```bash
./scripts/build-sovereign-image.sh
```

See [image-builder/README.md](image-builder/README.md) for prerequisites, outputs, and qualification boundaries.

## Contributing

The project follows a specification-driven workflow. Changes should be grounded in the active phase, relevant RFCs or decisions, explicit acceptance criteria, and proportionate verification.

See [AGENTS.md](AGENTS.md) for branch, commit, and pull-request conventions and [docs/development/workflow.md](docs/development/workflow.md) for the development process.

## License

Sovereign OS is licensed under the [GNU Affero General Public License v3.0](LICENSE).
