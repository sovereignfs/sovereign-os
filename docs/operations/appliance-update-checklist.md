# Appliance Update Release Checklist

**Status:** Draft  
**Applies to:** Milestone 01.1 update artifacts

## Release Definition

- [ ] Appliance version assigned.
- [ ] Supported source versions declared.
- [ ] Compatible device identifiers declared.
- [ ] Component versions and Pi-hole digest recorded.
- [ ] Migration and schema versions recorded.
- [ ] Required free storage recorded.
- [ ] Reboot requirement recorded.
- [ ] Rollback limitations documented.
- [ ] Update and clean-image manifests agree on component versions.

## Artifact Trust

- [ ] Manifest schema validates.
- [ ] Manifest is signed by an approved release key.
- [ ] Key identifier and rotation status are valid.
- [ ] Every payload has a cryptographic digest and size.
- [ ] Pi-hole OCI artifact matches the declared digest.
- [ ] Development/test signing keys are not trusted by the release channel.
- [ ] Tampered manifest and payload tests fail.

## Compatibility and Safety

- [ ] Update tested from every supported source version.
- [ ] Wrong-device update is rejected.
- [ ] Unsupported source version is rejected.
- [ ] Downgrade policy is enforced.
- [ ] Insufficient disk space is detected before mutation.
- [ ] Concurrent update attempt is rejected.
- [ ] Existing system health is recorded before update.

## Backup and Persistent Data

- [ ] Pi-hole data is mounted from `/data/sovereign`.
- [ ] Pi-hole administrator credential remains unchanged.
- [ ] Backup completes before activation.
- [ ] Backup contents and readability are validated.
- [ ] Backup retention and cleanup are bounded.
- [ ] Restore has been tested on a separate copy or test device.
- [ ] Sensitive backup permissions are correct.

## Staging and Validation

- [ ] Payload is staged outside the active release.
- [ ] Archive traversal, unsafe links, ownership, and modes are rejected.
- [ ] Versioned release directory is complete before activation.
- [ ] Compose configuration validates.
- [ ] Nginx configuration validates.
- [ ] systemd unit content and enablement changes are reviewed.
- [ ] Migration preconditions pass.
- [ ] Update journal reaches `staged` before service interruption.

## Activation and Health

- [ ] Active release switches atomically.
- [ ] Expected services stop and start in dependency order.
- [ ] Pi-hole container runs at the declared digest.
- [ ] TCP DNS check passes.
- [ ] UDP DNS check passes.
- [ ] Local health is distinguished from upstream internet availability.
- [ ] `/dns/admin/` check passes.
- [ ] `/dns/api/` behavior passes.
- [ ] Root `/admin/*` and `/api/*` remain outside Pi-hole.
- [ ] Persistent data remains mounted from `/data`.
- [ ] Update commits only after all mandatory checks pass.

## Failure and Rollback

- [ ] Failure injected at each transaction state.
- [ ] Interrupted download resumes or restarts safely.
- [ ] Interrupted staging cleans up safely.
- [ ] Interruption during activation is recoverable.
- [ ] Failed health check triggers rollback.
- [ ] Previous appliance release is restored.
- [ ] Previous Pi-hole digest is restored.
- [ ] Data backup is restored when required.
- [ ] Rollback health checks pass.
- [ ] Rollback failure produces `recovery_required` with actionable instructions.
- [ ] Household DNS recovery procedure is verified.

## Privacy and Diagnostics

- [ ] Update requests contain no unnecessary device or Pi-hole data.
- [ ] Credentials and DNS query data are absent from update logs.
- [ ] Journal permissions are correct.
- [ ] Diagnostic output is useful without exposing secrets.
- [ ] No mandatory telemetry was introduced.

## Documentation and Approval

- [ ] Release notes explain user-visible changes.
- [ ] Update command and expected downtime documented.
- [ ] Backup and rollback behavior documented.
- [ ] Migration and rollback limitations emphasized.
- [ ] Recovery procedure updated.
- [ ] Security review complete.
- [ ] Real Raspberry Pi verification complete.
- [ ] Project owner approves publication.

