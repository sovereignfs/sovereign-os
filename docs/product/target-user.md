# Initial Target User

**Status:** Draft  
**Version:** 0.1

## Primary User

The first user is the project creator: a software developer who values privacy, already experiments with self-hosted systems, owns a Raspberry Pi 5 with 16 GB RAM, and wants a useful system in their own home rather than a technology demonstration that is immediately discarded.

This user can prepare a Raspberry Pi and follow technical installation instructions. They should not need to manually coordinate containers, inspect databases, construct API requests, or read service logs during ordinary use.

## Needs

- Operate useful home services without depending on a proprietary cloud ecosystem.
- Understand the state of local services through a coherent interface.
- Ask natural-language questions without granting an AI unrestricted system access.
- Retain ownership of hardware, data, credentials, backups, and provider choices.
- Continue receiving useful core behavior when the internet is unavailable.
- Install, recover, and remove the system through documented procedures.

## Initial Context

- One home and one administrator.
- A trusted local network, but not an assumption that every local device is benign.
- A Raspberry Pi dedicated to, or suitable for, persistent services.
- Pi-hole available on the same host or elsewhere on the local network.
- Browser access from a phone, tablet, or computer.
- Limited spare time for ongoing administration.

## Success for This User

Phase 01 succeeds when the user can flash one image, boot the Raspberry Pi, reach Pi-hole at `sovereign.local/dns/admin/`, and use it as the household DNS service without installing packages or running setup commands. Router DNS configuration remains an explicit external step.

## Users Not Yet Targeted

- Non-technical consumers expecting appliance-level installation and support.
- Multi-household or enterprise administrators.
- Users requiring remote access over the public internet.
- Users requiring broad hardware compatibility.
- Plugin developers outside the core project.
- Users seeking a finished voice-assistant replacement in the preview.

These may become future audiences, but they must not distort the first vertical slice.
