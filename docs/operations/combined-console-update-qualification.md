# Combined Console and Appliance Update Qualification

**Status:** Ready for the next Raspberry Pi image cycle

## Purpose

Qualify the deferred Sovereign Console work and the first Pi-hole-only appliance
update transaction in one hardware cycle. This is an engineering procedure for
a trusted LAN, not a production signing-key ceremony.

## Required Candidates

1. Build and flash a base candidate such as `0.1.0-preview.6` from current
   `main`, without an update candidate.
2. Build a target candidate such as `0.1.0-preview.7` with **Build update
   candidate** enabled, source minimum `0.1.0-preview.6`, source maximum
   exclusive `0.2.0`, and key ID `preview-local`.
3. Download the second workflow artifact. Its `update-release/` directory
   contains the unsigned exact-byte manifest and update bundle.

## Local Engineering Key

Generate the private key on the operator machine. Never add it to the
repository, Actions, an image, or a diagnostic bundle.

```bash
openssl genpkey -algorithm Ed25519 -out sovereign-preview-local-private.pem
chmod 600 sovereign-preview-local-private.pem
openssl pkey -in sovereign-preview-local-private.pem -pubout \
  -out preview-local.pem

./scripts/sign-update-manifest.py \
  --manifest update-release/release-manifest.json \
  --private-key sovereign-preview-local-private.pem \
  --output update-release/release-manifest.sig
```

Create `preview-local.json` beside the public key:

```json
{
  "schema_version": 1,
  "key_id": "preview-local",
  "algorithm": "Ed25519",
  "channels": ["preview"],
  "revoked": false
}
```

Copy only the public files and update inputs to the Pi, then install trust:

```bash
sudo install -m 0644 preview-local.pem preview-local.json \
  /etc/sovereign/update-trust.d/
```

## Console Baseline

```bash
curl -fsS http://sovereign.local/console/ >/dev/null
curl -fsS http://sovereign.local/console/health/ >/dev/null
curl -fsS http://sovereign.local/api/v1/health | python3 -m json.tool
curl -fsS http://sovereign.local/dns/admin/ >/dev/null
sudo sha256sum /data/sovereign/secrets/pihole-admin-password
readlink -f /opt/sovereign/current
sudo find /data/sovereign/apps/pihole/etc-pihole -maxdepth 1 -type f -ls
```

Record the output without displaying the password itself.

## Transaction

Inspect without mutation:

```bash
sovereign-update inspect \
  --manifest release-manifest.json \
  --signature release-manifest.sig \
  --artifact sovereign-update-0.1.0-preview.7-rpi5-arm64.tar.zst
```

Prepare and capture the returned transaction ID, then cross each explicit
privileged boundary:

```bash
sudo sovereign-update prepare \
  --manifest release-manifest.json \
  --signature release-manifest.sig \
  --artifact sovereign-update-0.1.0-preview.7-rpi5-arm64.tar.zst

sudo sovereign-update backup <transaction-id>
sudo sovereign-update stage <transaction-id>
sudo sovereign-update activate <transaction-id>
sovereign-update status
```

Re-run the baseline. The transaction must be `committed`, the active version
must be the target, and Pi-hole credentials and persistent files must be
unchanged.

## Forced Rollback Qualification

For a separate prepared, backed-up, and staged transaction, force only the
post-activation health command to fail:

```bash
sudo env SOVEREIGN_UPDATE_HEALTH_CHECK=/bin/false \
  sovereign-update activate <transaction-id>
```

The command must fail, the journal must end at `rolled_back`, and the active
pointer must resolve to the previous release. Pi-hole, TCP/UDP DNS,
`/dns/admin/`, and Console must be healthy afterward.

## Reboot Recovery Qualification

Power interruption tests are required at `backing_up`, `activating`, and
`validating`. On the next boot, `sovereign-update-recovery.service` must restore
the recorded previous pointer for interrupted activation, mark the transaction
`recovery_required`, and allow the previous Pi-hole release to start. It must
never infer a commit.

## Exit Evidence

- Console screenshots for healthy, degraded, committed, and rolled-back states
- Health API documents with secrets removed from any shared copy
- Transaction `state.json` and non-secret `events.jsonl`
- Backup manifest and archive size/digest checks
- Before/after active release and password digests
- TCP and UDP DNS, HTTP routing, reboot, and persistence results
- Exact image/update versions and source revisions
