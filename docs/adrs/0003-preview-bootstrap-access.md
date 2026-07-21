# ADR-0003: Preview Bootstrap Access

**Status:** Accepted for the Phase 01 preview  
**Date:** 2026-07-21  
**Decision owner:** Project creator  
**Related RFC:** [RFC-0010](../rfcs/0010-raspberry-pi-image-deployment.md)

## Context

The first physical POC proved that Sovereign OS boots, joins an Ethernet
network, advertises `sovereign.local`, serves Pi-hole, and answers DNS queries.
It also exposed a headless-onboarding dead end: an image flashed without
Raspberry Pi Imager customisation has no accepted SSH credential, while the
generated Pi-hole password is readable only from the physical console or a
privileged shell.

Requiring a release manifest, a compatible pre-release Imager, and an SSH key
before a user can inspect the appliance is too much friction for the preview.

## Decision

Phase 01 preview images will provide a temporary bootstrap account:

- username: `sovereign`;
- initial password: `sovereign`;
- SSH enabled on the local network with password authentication;
- root SSH login disabled; and
- the bootstrap password expired so the user must replace it at the first
  successful interactive login before receiving a shell.

The image must clearly label this credential as public and temporary. Users
must connect only from a trusted local network, change the password
immediately, and should install an SSH public key and disable password
authentication after onboarding.

Ethernet remains the zero-configuration network path. A logged-in user may
configure Wi-Fi later with IWD. Raspberry Pi Imager provisioning remains an
optional way to install a user-selected account, SSH key, and Wi-Fi settings
while flashing.

This exception applies only to preview builds. A production release requires a
device-unique bootstrap secret, secure claim flow, or equivalent mechanism.

## Consequences

### Positive

- A headless Ethernet installation is recoverable without reflashing.
- Users can retrieve the unique Pi-hole password and diagnose services.
- The normal custom-image flashing path no longer depends on manifest support.
- Wi-Fi and SSH keys can be configured after first boot.

### Negative

- Every unclaimed preview device has a publicly known LAN credential.
- Forced password change protects subsequent access, not the interval before
  the first login.
- A hostile device on the same network could claim the account first.
- Password authentication adds brute-force exposure on untrusted networks.

## Required Controls

- Document the credential beside every preview download and flashing guide.
- Never expose SSH through router port forwarding or a public interface.
- Force password replacement using account-expiry semantics; a banner or
  recommendation alone is insufficient.
- Generate unique SSH host keys on first boot.
- Keep root login disabled and do not grant passwordless sudo by default.
- Test that the initial password cannot open a second session after it has been
  changed.
- Provide documented key installation and password-authentication hardening.
- Replace this design before removing the preview label.

## Rejected Alternatives

### Require Raspberry Pi Imager provisioning

This is safer but failed the simplest downloaded-image workflow and depends on
custom manifest compatibility.

### Display credentials only on an attached console

This excludes headless users and was the failure observed in the physical POC.

### Publish the Pi-hole password directly

This would expose an application administrator secret and still would not
provide host diagnostics or Wi-Fi configuration.

