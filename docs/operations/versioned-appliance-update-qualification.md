# Versioned Appliance Update Qualification

**Status:** Ready for Raspberry Pi execution

## Purpose

Qualify the first update in which Console assets, Nginx routing, Compose,
lifecycle programs, and health checks are activated behind the same release
pointer as the Pi-hole image metadata. This procedure verifies the new stable
dispatch boundary; it does not qualify persistent-data restore or base-OS
replacement.

## Candidates

Build both candidates from the same `main` revision:

1. `0.1.0-preview.9`: full image, without an update candidate. Flash this image.
2. `0.1.0-preview.10`: build with an update candidate, source minimum
   `0.1.0-preview.9`, source maximum exclusive `0.2.0`, and key ID
   `preview-local`.

The separate versions render different static Console footers even though the
source is identical. The preview.9 image is mandatory because older images do
not contain the stable versioned dispatch boundary.

## Prepare the Qualification Kit

On the operator machine, generate an ephemeral engineering key and prepare the
private-key-free kit from preview.10's downloaded `update-release/` directory:

```bash
openssl genpkey -algorithm Ed25519 -out sovereign-preview-local-private.pem
chmod 600 sovereign-preview-local-private.pem

./scripts/prepare-update-qualification.py \
  --update-dir update-release \
  --private-key sovereign-preview-local-private.pem \
  --output-dir preview-10-qualification-kit \
  --key-id preview-local

cd preview-10-qualification-kit
shasum -a 256 --check SHA256SUMS
cd ..
scp -r preview-10-qualification-kit \
  sovereign@sovereign.local:~/update-qualification
```

Install only the public trust files on the Pi:

```bash
cd ~/update-qualification
sudo install -m 0644 preview-local.pem preview-local.json \
  /etc/sovereign/update-trust.d/
sha256sum --check SHA256SUMS
bundle=$(python3 -c \
  'import json; print(json.load(open("qualification-kit.json"))["bundle"])')
```

## Baseline

The flashed base must expose preview.9 through both release metadata and the
static versioned Console asset:

```bash
test "$(readlink -f /opt/sovereign/current)" = \
  /opt/sovereign/releases/0.1.0-preview.9
curl -fsS http://sovereign.local/console/ | \
  grep -F 'Release 0.1.0-preview.9'
curl -fsS http://sovereign.local/api/v1/health | python3 -m json.tool
curl -fsS http://sovereign.local/dns/admin/ >/dev/null
sudo /opt/sovereign/current/appliance/bin/verify-update-health
```

Create an on-device, root-only credential continuity reference:

```bash
sudo sh -c 'sha256sum /data/sovereign/secrets/pihole-admin-password > \
  /data/sovereign/update-state/qualification-password.sha256'
```

## Transaction Helper

```bash
prepare_and_stage() {
  sudo sovereign-update prepare \
    --manifest release-manifest.json \
    --signature release-manifest.sig \
    --artifact "$bundle" > .qualification-prepare.json || return
  transaction=$(python3 -c \
    'import json; print(json.load(open(".qualification-prepare.json"))["transaction_id"])')
  printf '%s\n' "$transaction" > .qualification-transaction
  sudo sovereign-update backup "$transaction" || return
  sudo sovereign-update stage "$transaction" || return
  printf '%s\n' "$transaction"
}
```

After staging, the inactive target must contain the rendered asset while the
served Console remains preview.9:

```bash
grep -F 'Release 0.1.0-preview.10' \
  /opt/sovereign/releases/0.1.0-preview.10/appliance/console/index.html
curl -fsS http://sovereign.local/console/ | \
  grep -F 'Release 0.1.0-preview.9'
```

## Interrupted Validation Recovery

```bash
transaction=$(prepare_and_stage)
set +e
sudo env SOVEREIGN_UPDATE_QUALIFICATION=1 \
  SOVEREIGN_UPDATE_QUALIFICATION_INTERRUPT=validating \
  sovereign-update activate "$transaction"
result=$?
set -e
test "$result" -eq 75
sudo reboot
```

After reconnecting, boot recovery must restore preview.9 before normal services
start:

```bash
cd ~/update-qualification
transaction=$(cat .qualification-transaction)
test "$(readlink -f /opt/sovereign/current)" = \
  /opt/sovereign/releases/0.1.0-preview.9
curl -fsS http://sovereign.local/console/ | \
  grep -F 'Release 0.1.0-preview.9'
sudo /opt/sovereign/current/appliance/bin/verify-update-health
sudo sovereign-update discard "$transaction"
```

## Forced Health Rollback

```bash
transaction=$(prepare_and_stage)
set +e
sudo env SOVEREIGN_UPDATE_QUALIFICATION=1 \
  SOVEREIGN_UPDATE_QUALIFICATION_FAIL_HEALTH=1 \
  sovereign-update activate "$transaction"
result=$?
set -e
test "$result" -eq 2
test "$(readlink -f /opt/sovereign/current)" = \
  /opt/sovereign/releases/0.1.0-preview.9
curl -fsS http://sovereign.local/console/ | \
  grep -F 'Release 0.1.0-preview.9'
sudo /opt/sovereign/current/appliance/bin/verify-update-health
sudo sovereign-update discard "$transaction"
```

The transaction must end at `rolled_back`. Pi-hole, Console, Nginx, and the
local-access verifier must all run through preview.9 again.

## Successful Activation and Reboot

```bash
transaction=$(prepare_and_stage)
sudo sovereign-update activate "$transaction"
test "$(readlink -f /opt/sovereign/current)" = \
  /opt/sovereign/releases/0.1.0-preview.10
curl -fsS http://sovereign.local/console/ | \
  grep -F 'Release 0.1.0-preview.10'
sudo /opt/sovereign/current/appliance/bin/verify-update-health
sudo sha256sum --check \
  /data/sovereign/update-state/qualification-password.sha256
sudo reboot
```

After reconnecting, repeat the pointer, Console marker, complete health, and
credential checks. Confirm DATA is still a dedicated mount and the update state
is `committed`:

```bash
findmnt -rn -o TARGET /data | grep -qx /data
sovereign-update status
systemctl --failed
```

## Cleanup and Exit Evidence

Remove the temporary trust and credential reference only after recording
non-secret evidence:

```bash
sudo rm /etc/sovereign/update-trust.d/preview-local.pem \
  /etc/sovereign/update-trust.d/preview-local.json
sudo rm /data/sovereign/update-state/qualification-password.sha256
rm -rf ~/update-qualification
```

Delete the private key and local qualification kit from the operator machine.
Record exact source revision, workflow run IDs, pointer/Console versions,
transaction states, backup manifest roles, health output, service status,
credential continuity result, and DATA mount result. Do not record credentials,
private keys, DNS queries, or other household data.
