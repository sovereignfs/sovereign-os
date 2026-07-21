# First Login and Network Setup

**Status:** Implemented; physical image verification pending

This guide defines the Phase 01 preview onboarding flow. Images released before
the bootstrap-account implementation do not provide this behavior.

## 1. Boot on a Trusted Ethernet Network

Flash the image, connect Ethernet, and power on the Raspberry Pi. Do not expose
the preview appliance directly to the internet. Allow several minutes for the
first boot, then verify discovery from another computer:

```bash
ping sovereign.local
```

If `.local` discovery is unavailable, find the address in the router's DHCP
client list and substitute it for `sovereign.local` below.

## 2. Perform the Mandatory First Login

Connect with the preview bootstrap account:

```bash
ssh sovereign@sovereign.local
```

Use `sovereign` as the initial password. SSH will require a new password before
opening the shell. Choose a unique password that is not used for another
account. The initial credential is public and must not remain active.

The expected interaction is:

```text
sovereign@sovereign.local's password: sovereign
WARNING: Your password has expired.
You must change your password now and login again!
Current password: sovereign
New password: <your-new-device-password>
Retype new password: <your-new-device-password>
```

The SSH connection may close after the change. Reconnect with the new password:

```bash
ssh sovereign@sovereign.local
```

## 3. Retrieve the Pi-hole Password

The Pi-hole password is unique to the device and remains separate from the
Linux account password:

```bash
sudo cat /data/sovereign/secrets/pihole-admin-password
```

Sign in at:

```text
http://sovereign.local/dns/admin/
```

To replace the generated Pi-hole password, run:

```bash
sudo sovereign-pihole-password
```

The command prompts without echoing the new value, updates Pi-hole, and updates
the root-owned persistent secret used when the container is recreated. The
Linux login password and Pi-hole password remain separate.

## 4. Add an SSH Key

On the client computer, create a key if needed:

```bash
ssh-keygen -t ed25519
```

Install it on the appliance:

```bash
ssh-copy-id sovereign@sovereign.local
```

Open a second terminal and verify key authentication before changing the SSH
server policy:

```bash
ssh -o PasswordAuthentication=no sovereign@sovereign.local
```

After that succeeds, disable password authentication on the appliance with a
local override that takes precedence over image and Imager defaults:

```bash
printf '%s\n' \
  'PermitRootLogin no' \
  'PasswordAuthentication no' \
  'KbdInteractiveAuthentication no' | \
  sudo tee /etc/ssh/sshd_config.d/90-local-auth.conf >/dev/null
sudo chmod 0600 /etc/ssh/sshd_config.d/90-local-auth.conf
sudo sshd -t
sudo systemctl reload ssh
```

Keep the verified session open until a new key-authenticated session succeeds.
If the key test fails, do not disable password authentication.

To re-enable password authentication later from an existing key-authenticated
session:

```bash
printf '%s\n' \
  'PermitRootLogin no' \
  'PasswordAuthentication yes' | \
  sudo tee /etc/ssh/sshd_config.d/90-local-auth.conf >/dev/null
sudo chmod 0600 /etc/ssh/sshd_config.d/90-local-auth.conf
sudo sshd -t
sudo systemctl reload ssh
```

## 5. Configure Wi-Fi Later

Set the regulatory country first, replacing `DE` with the correct two-letter
country code, and reboot to apply it:

```bash
echo 'options cfg80211 ieee80211_regdom=DE' | \
  sudo tee /etc/modprobe.d/cfg80211_regdomain.conf
sudo reboot
```

Reconnect over Ethernet after the reboot, then connect using IWD:

```bash
sudo iwctl
```

At the interactive prompt:

```text
device list
station wlan0 scan
station wlan0 get-networks
station wlan0 connect "YOUR_WIFI_NAME"
exit
```

IWD prompts for the Wi-Fi passphrase without placing it in shell history and
stores the resulting profile root-only. Confirm connectivity before removing
Ethernet:

```bash
ip address show wlan0
ping -c 3 sovereign.local
```

## 6. Recover Access

If password login still works but the SSH key does not, log in with the device
password, remove the local hardening override if present, and repeat the key
installation:

```bash
sudo rm -f /etc/ssh/sshd_config.d/90-local-auth.conf
sudo sshd -t
sudo systemctl reload ssh
```

If key authentication works but the Linux password was forgotten, reset it:

```bash
sudo passwd sovereign
```

If neither authentication method works, shut down the Pi, attach the storage to
a Linux system that can safely write ext4, mount the root partition, and add a
trusted public key to `/home/sovereign/.ssh/authorized_keys`. Preserve ownership
as UID/GID 1000 and modes `0700` for `.ssh` and `0600` for `authorized_keys`.
macOS does not provide safe native ext4 write support.

Reflashing the complete disk image is the final recovery option and erases the
existing partition table, including `/data`. Back up Pi-hole state before a
reflash whenever access to the data partition is still possible.

## Recovery Notes

- `Permission denied (publickey)` on an older image means that image has no
  usable bootstrap password flow; reflash a release that implements this ADR.
- The Linux password and Pi-hole administrator password are intentionally
  different.
- If the bootstrap password was not changed, treat the device as unclaimed and
  disconnect it from untrusted networks.
- Do not disable password authentication until key authentication has been
  tested in a separate session.
