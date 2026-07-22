# Combined Console and Appliance Update Qualification

**Status:** Ready for the next Raspberry Pi image cycle

## Purpose

Qualify the deferred Sovereign Console work and the first Pi-hole-only appliance
update transaction in one hardware cycle. This is an engineering procedure for
a trusted LAN, not a production signing-key ceremony.

## Required Candidates

1. Build and flash base candidate `0.1.0-preview.7` from current
   `main`, without an update candidate.
2. Build target candidate `0.1.0-preview.8` with **Build update
   candidate** enabled, source minimum `0.1.0-preview.7`, source maximum
   exclusive `0.2.0`, and key ID `preview-local`.
3. Download the second workflow artifact. Its `update-release/` directory
   contains the unsigned exact-byte manifest and update bundle.

Both candidates must come from the same reviewed source revision. The version
change is sufficient to exercise versioned staging and activation; a second
functional change is not required.

## Local Engineering Key

Generate the private key on the operator machine. Never add it to the
repository, Actions, an image, or a diagnostic bundle.

```bash
openssl genpkey -algorithm Ed25519 -out sovereign-preview-local-private.pem
chmod 600 sovereign-preview-local-private.pem

./scripts/prepare-update-qualification.py \
  --update-dir update-release \
  --private-key sovereign-preview-local-private.pem \
  --output-dir preview-8-qualification-kit \
  --key-id preview-local
```

The preparation tool:

- validates the manifest's artifact size and SHA-256 before signing;
- requires the private key to be inaccessible to group and other users;
- signs the exact manifest bytes and verifies the result with the derived
  public key;
- creates `preview-local.pem`, `preview-local.json`, `release-manifest.sig`,
  and `SHA256SUMS`; and
- never copies the private key into the qualification kit.

Verify and transfer the kit from the operator machine:

```bash
cd preview-8-qualification-kit
shasum -a 256 --check SHA256SUMS # macOS
cd ..
scp -r preview-8-qualification-kit \
  sovereign@sovereign.local:~/update-qualification
```

Copy only the public files and update inputs to the Pi, then install trust:

```bash
cd ~/update-qualification
sudo install -m 0644 preview-local.pem preview-local.json \
  /etc/sovereign/update-trust.d/
sha256sum --check SHA256SUMS
```

## Console Baseline

```bash
curl -fsS http://sovereign.local/console/ >/dev/null
curl -fsS http://sovereign.local/console/health/ >/dev/null
curl -fsS http://sovereign.local/api/v1/health | python3 -m json.tool
curl -fsS http://sovereign.local/dns/admin/ >/dev/null
readlink -f /opt/sovereign/current
sudo find /data/sovereign/apps/pihole/etc-pihole -maxdepth 1 -type f -ls
```

Record the output without displaying the password itself.

Create a root-only, volatile continuity reference instead of exporting a
password hash into shared evidence:

```bash
sudo sh -c 'sha256sum /data/sovereign/secrets/pihole-admin-password > \
  /data/sovereign/update-state/qualification-password.sha256'
```

## Transaction Helpers

Run the remaining commands on the Pi from `~/update-qualification`:

```bash
cd ~/update-qualification
bundle=$(python3 -c \
  'import json; print(json.load(open("qualification-kit.json"))["bundle"])')

prepare_transaction() {
  sudo sovereign-update prepare \
    --manifest release-manifest.json \
    --signature release-manifest.sig \
    --artifact "$bundle" > .qualification-prepare.json || return
  python3 -c \
    'import json; print(json.load(open(".qualification-prepare.json"))["transaction_id"])' \
    > .qualification-transaction
  cat .qualification-transaction
}

prepare_and_stage() {
  transaction=$(prepare_transaction) || return
  sudo sovereign-update backup "$transaction" || return
  sudo sovereign-update stage "$transaction" || return
  printf '%s\n' "$transaction"
}
```

`sovereign-update inspect` remains a non-mutating check and should pass before
the first prepared transaction:

```bash
sovereign-update inspect \
  --manifest release-manifest.json \
  --signature release-manifest.sig \
  --artifact "$bundle"
```

## Deterministic Reboot Recovery

The updater contains an explicitly armed qualification hook. It exits with
status 75 immediately after the requested transition has been atomically
written and fsynced. Without both environment variables, the hook cannot run.

Test `backing_up` first:

```bash
transaction=$(prepare_transaction)
set +e
sudo env SOVEREIGN_UPDATE_QUALIFICATION=1 \
  SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT=backing_up \
  sovereign-update backup "$transaction"
result=$?
set -e
test "$result" -eq 75
sudo reboot
```

After the Pi returns, verify `recovery_required`, the base release, Console,
Pi-hole, and TCP/UDP DNS. Then retain the journal and backup evidence while
removing only inactive transient payloads:

```bash
cd ~/update-qualification
transaction=$(cat .qualification-transaction)
sovereign-update status
test "$(readlink -f /opt/sovereign/current)" = \
  /opt/sovereign/releases/0.1.0-preview.7
sudo sovereign-update discard "$transaction"
```

Repeat the prepare/backup/stage cycle for `activating` and `validating`:

```bash
transaction=$(prepare_and_stage)
set +e
sudo env SOVEREIGN_UPDATE_QUALIFICATION=1 \
  SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT=activating \
  sovereign-update activate "$transaction"
result=$?
set -e
test "$result" -eq 75
sudo reboot
```

After recovery and health verification, run
`sudo sovereign-update discard "$transaction"`. Repeat with
`SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT=validating`. The validating case
must restore the preview.7 pointer on boot before Pi-hole starts. `discard`
must refuse to remove a target if it is active; it preserves `state.json`,
`events.jsonl`, and the referenced backup.

After each reconnect, return to `~/update-qualification`, restore
`transaction=$(cat .qualification-transaction)`, and re-run the Transaction
Helpers block before starting the next fresh transaction.

## Forced Rollback Qualification

Run forced rollback before the final successful update so the same target
version remains a valid upgrade:

```bash
transaction=$(prepare_and_stage)
set +e
sudo env SOVEREIGN_UPDATE_QUALIFICATION=1 \
  SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH=1 \
  sovereign-update activate "$transaction"
result=$?
set -e
test "$result" -eq 2
sudo sovereign-update discard "$transaction"
```

The journal must end at `rolled_back`; the active release must remain
preview.7, and Pi-hole, TCP/UDP DNS, `/dns/admin/`, and Console must be healthy.

## Successful Transaction

Inspect without mutation:

```bash
sovereign-update inspect \
  --manifest release-manifest.json \
  --signature release-manifest.sig \
  --artifact "$bundle"
```

Prepare and capture the returned transaction ID, then cross each explicit
privileged boundary:

```bash
transaction=$(prepare_and_stage)
sudo sovereign-update activate "$transaction"
sovereign-update status
```

Re-run the baseline and reboot once. The transaction must remain `committed`,
the active version must remain preview.8, and Pi-hole credentials and
persistent files must be unchanged. Verify the on-device continuity reference
without printing the digest:

```bash
sudo sha256sum --check \
  /data/sovereign/update-state/qualification-password.sha256
sudo rm /data/sovereign/update-state/qualification-password.sha256
```

## Exit Evidence

- Console screenshots for healthy, degraded, committed, and rolled-back states
- Health API documents with secrets removed from any shared copy
- Transaction `state.json` and non-secret `events.jsonl`
- Backup manifest and archive size/digest checks
- Before/after active release and password digests
- TCP and UDP DNS, HTTP routing, reboot, and persistence results
- Exact image/update versions and source revisions
