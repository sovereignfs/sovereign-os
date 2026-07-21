# Raspberry Pi Imager Provisioning

**Status:** Implemented; physical Raspberry Pi 5 verification pending

## Purpose

Sovereign OS accepts Raspberry Pi Imager's `rpi-preseed` customization file on
first boot. This lets a user put Wi-Fi and an SSH public key into a freshly
flashed device without modifying the Linux filesystems by hand or connecting a
keyboard and display.

The downloadable image itself contains no user credential. Imager writes the
per-device settings to the boot partition during flashing. Sovereign consumes
that file before networking and SSH start, then deletes it from the boot
partition.

## Flash with Customization

This workflow requires Raspberry Pi Imager 2.0.11 or later. Earlier Imager 2.x
releases reject `rpi-preseed` manifests and silently omit the Sovereign OS entry
from the operating-system list. While 2.0.11 is available only as a release
candidate, use the official 2.0.11-rc1 build for POC qualification.

Download the complete release bundle and verify it from inside its directory:

```bash
sha256sum --check SHA256SUMS
```

Create the small local Imager catalog beside the downloaded image:

```bash
python3 create-imager-manifest.py \
  sovereign-os-0.1.0-preview.1-rpi5-arm64.img.zst \
  --version 0.1.0-preview.1
```

If Imager 2.0.11-rc1 reports the compressed-file SHA-256 as the "Actual"
uncompressed hash, decompress the local image and generate the manifest from
the raw file instead:

```bash
zstd --decompress sovereign-os-0.1.0-preview.1-rpi5-arm64.img.zst \
  --output sovereign-os-0.1.0-preview.1-rpi5-arm64.img
python3 create-imager-manifest.py \
  sovereign-os-0.1.0-preview.1-rpi5-arm64.img \
  --version 0.1.0-preview.1
```

This preserves full SHA-256 verification but requires approximately 3.2 GB of
additional local disk space for the current image.

Open `sovereign-os.rpi-imager-manifest` with Raspberry Pi Imager. Select the
Sovereign OS entry, select the target storage, and configure:

- the Wi-Fi SSID, password, and country when Ethernet will not be used;
- SSH with a public key, which is the recommended diagnostic access method;
- the operator username and password if desired; and
- timezone.

Keep the hostname as `sovereign`. The appliance owns that hostname so its local
address remains `sovereign.local`. Write the image, insert the storage into the
Pi, and power it on.

On a compatible Raspberry Pi Imager, selecting the `.img.zst` through **Use custom** does
not advertise an initialization format and therefore does not present OS
customization. Open the supplied `.rpi-imager-manifest` instead.

## First-Boot Behavior

`sovereign-imager-provision.service` runs before IWD, SSH, and the Sovereign
appliance services. It supports the following `rpi-preseed` settings:

- operator username, encrypted password, supplementary groups, and optional
  passwordless sudo;
- SSH authorized keys and optional password authentication;
- open, WPA-PSK, and SAE Wi-Fi, including hidden SSIDs and a regulatory country;
- timezone.

Wi-Fi is translated to a root-only IWD network profile. SSH remains configured
with root login disabled. Key authentication is recommended; the base image
does not ship a shared login password.

The hostname is intentionally fixed to `sovereign`; a different Imager value is
ignored. Raspberry Pi Connect and custom network-interface definitions are not
part of this POC.

After success, non-secret status is recorded at:

```text
/data/sovereign/imager-provisioning.json
/data/sovereign/imager-provisioned
```

The source credential file at `/boot/firmware/rpi-preseed.toml` is removed as
soon as it has been parsed, including when validation fails. A failed initial
configuration must be corrected by flashing again; Sovereign does not preserve
the credential-bearing input for retry.

## Connect

Allow several minutes for initial appliance setup, then try:

```bash
ssh <operator>@sovereign.local
```

If mDNS is unavailable, find the address in the router's DHCP client list and
use `ssh <operator>@<address>`. The web entry point is
`http://sovereign.local/`, with the direct IP as a fallback.

## Compatibility Boundary

This is a Sovereign-owned compatible consumer of the documented Raspberry Pi
Imager `rpi-preseed` format, not the Raspberry Pi `rpi-preseed` Debian package.
The supported subset is tested in this repository and must be qualified with
the current Imager release and a physical Raspberry Pi 5 before publication.

## Sources

- [Raspberry Pi Imager and OS customization](https://www.raspberrypi.com/documentation/computers/getting-started.html)
- [Raspberry Pi Imager OS customization formats](https://github.com/raspberrypi/rpi-imager/blob/main/doc/os_customisation_formats.md)
- [IWD network configuration](https://kernel.googlesource.com/pub/scm/network/wireless/iwd/+/refs/tags/3.4/src/iwd.network.rst)
