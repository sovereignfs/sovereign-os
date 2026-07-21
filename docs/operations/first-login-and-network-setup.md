# First Login and Network Setup

**Status:** Approved process; image implementation pending

This guide defines the Phase 01 preview onboarding flow. It does not describe
the behavior of images released before the bootstrap-account implementation.

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

After that succeeds, disable password authentication on the appliance:

```bash
sudo sed -i 's/^PasswordAuthentication .*/PasswordAuthentication no/' \
  /etc/ssh/sshd_config.d/10-sovereign.conf
sudo sshd -t
sudo systemctl reload ssh
```

Keep the verified session open until a new key-authenticated session succeeds.
If the key test fails, do not disable password authentication.

## 5. Configure Wi-Fi Later

Set the regulatory country first, replacing `DE` with the correct two-letter
country code:

```bash
echo 'options cfg80211 ieee80211_regdom=DE' | \
  sudo tee /etc/modprobe.d/cfg80211_regdomain.conf
sudo modprobe -r brcmfmac
sudo modprobe brcmfmac
```

Then connect using IWD:

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

If reloading the Wi-Fi driver would interrupt another active connection, write
the regulatory setting and reboot instead.

## Recovery Notes

- `Permission denied (publickey)` on an older image means that image has no
  usable bootstrap password flow; reflash a release that implements this ADR.
- The Linux password and Pi-hole administrator password are intentionally
  different.
- If the bootstrap password was not changed, treat the device as unclaimed and
  disconnect it from untrusted networks.
- Do not disable password authentication until key authentication has been
  tested in a separate session.

