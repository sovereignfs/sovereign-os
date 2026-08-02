#!/bin/bash

set -eu

filesystem=$1
genimage_input=$2

source "${IGconf_image_outputdir}/img_uuids"

# --- Static tryboot control file (RFC-0016) ---
# Partition numbers match genimage.cfg.in exactly: 1=bootconfig,
# 2=boot_a, 3=boot_b. A normal boot uses [all]'s boot_partition (2,
# boot_a) unconditionally; a trial boot (userspace-triggered via
# `reboot "0 tryboot"`, never by editing this file at runtime) uses
# [tryboot]'s boot_partition (3, boot_b) for exactly one boot. Firmware
# promotes the trial slot on the next *ordinary* reboot that follows a
# tryboot session -- nothing in this image rewrites autoboot.txt at
# runtime. See rpi-slot-tryboot (rpi-ab-slot-mapper) for the equivalent
# logic used after the first slot switch, once "active"/"other" can
# differ from this initial default.
cat << EOF > "${genimage_input}/autoboot.txt"
[all]
tryboot_a_b=1
boot_partition=2
[tryboot]
boot_partition=3
EOF

# --- Template substitution ---
MKE2FS_ROOT="-U $ROOT_UUID ${IGconf_fs_ext4_mkfs_args:-}"
MKE2FS_DATA="${IGconf_fs_ext4_mkfs_args:-}"
VFAT_ARGS="-S $IGconf_device_sector_size -i $BOOT_LABEL ${IGconf_fs_vfat_mkfs_args:-}"

sed \
  -e "s|<IMAGE_NAME>|$IGconf_image_name|g" \
  -e "s|<IMAGE_SUFFIX>|$IGconf_image_suffix|g" \
  -e "s|<SECTOR_SIZE>|$IGconf_device_sector_size|g" \
  -e "s|<BOOTCONFIG_SIZE>|$IGconf_image_bootconfig_part_size|g" \
  -e "s|<BOOT_SIZE>|$IGconf_image_boot_part_size|g" \
  -e "s|<ROOT_SIZE>|$IGconf_image_root_part_size|g" \
  -e "s|<DATA_SIZE>|$IGconf_image_data_part_size|g" \
  -e "s|<SETUP>|'$(readlink -ef setup.sh)'|g" \
  -e "s|<MKE2FS_CONF>|'$(readlink -ef mke2fs.conf)'|g" \
  -e "s|<MKE2FS_ROOT>|$MKE2FS_ROOT|g" \
  -e "s|<MKE2FS_DATA>|$MKE2FS_DATA|g" \
  -e "s|<VFAT_ARGS>|$VFAT_ARGS|g" \
  -e "s|<BOOT_LABEL>|$BOOT_LABEL|g" \
  -e "s|<ROOT_UUID>|$ROOT_UUID|g" \
  -e "s|<BOOT_UUID>|$BOOT_UUID|g" \
  genimage.cfg.in > "${genimage_input}/genimage.cfg"

# --- /data skeleton (existing Sovereign layout, unchanged) ---
install -d -m 0755 "${filesystem}/data/sovereign"
install -d -m 0755 "${filesystem}/data/sovereign/apps/pihole/etc-pihole"
install -d -m 0700 "${filesystem}/data/sovereign/secrets"
install -d -m 0711 "${filesystem}/data/docker" "${filesystem}/data/containerd"

# --- /opt/sovereign backing storage, on /data (RFC-0016) ---
# /opt/sovereign itself stays a plain directory in root (bind-mounted
# over at boot -- see setup.sh's fstab entry); this is where that mount
# actually lives, so appliance updates (RFC-0014) survive a base-OS
# slot switch instead of reverting to whatever a new root image shipped.
if [ -d "${filesystem}/opt/sovereign" ]; then
  install -d -m 0755 "${filesystem}/data/sovereign/releases"
  rsync -aHAX --numeric-ids "${filesystem}/opt/sovereign/" "${filesystem}/data/sovereign/releases/"
  # Reclaim from root: /opt/sovereign becomes a plain empty mount point
  # there, with its real content living only under /data (bind-mounted
  # back over it at boot by setup.sh's fstab entry) -- baking a second,
  # immediately-stale copy into read-only root would be dead weight and
  # a diverging-content trap the moment an appliance update runs.
  find "${filesystem}/opt/sovereign" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
fi

# --- Persistent home directories (RFC-0016) ---
# /etc's own persistence is handled at boot by sovereign-etc-overlay.service
# (an overlayfs with a writable upper layer on /data), not seeded here --
# passwd/usermod/PAM need the whole /etc directory writable (they rename a
# sibling temp file over the target), which a plain bind mount of individual
# files like /etc/passwd can't provide. /home gets the simpler bind-mount
# treatment: imager-provisioned SSH authorized_keys must survive a base-OS
# slot switch instead of reverting to build-time (empty) defaults.
if [ -d "${filesystem}/home" ]; then
  install -d -m 0755 "${filesystem}/data/sovereign/identity/home"
  rsync -aHAX --numeric-ids "${filesystem}/home/" "${filesystem}/data/sovereign/identity/home/"
  find "${filesystem}/home" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
fi

# --- machine-id, preserved across slot switches ---
# Must run before /var is reclaimed below -- it writes into
# /var/lib/dbus, which the reclaim step below empties out.
rm -f "${filesystem}/etc/machine-id" "${filesystem}/var/lib/dbus/machine-id"
install -m 0644 -o root -g root /dev/null "${filesystem}/etc/machine-id"
ln -sf /etc/machine-id "${filesystem}/var/lib/dbus/machine-id"

# --- Per-slot /var (RFC-0016) ---
# Root is read-only at runtime, so /var must be bind-mounted from
# somewhere writable. Kept per-slot (not shared between root_a/root_b)
# so one slot's software never writes state the other slot's software
# has to interpret -- both slots start identical here; they can only
# diverge after an actual base-OS update writes new content to the
# inactive slot.
install -d -m 0755 "${filesystem}/data/sovereign/slots/system_a" \
                     "${filesystem}/data/sovereign/slots/system_b"
rsync -aHAXS --numeric-ids --delete "${filesystem}/var/" "${filesystem}/data/sovereign/slots/system_a/var/"
rsync -aHAXS --numeric-ids --delete "${filesystem}/var/" "${filesystem}/data/sovereign/slots/system_b/var/"

# Reclaim /var in the image itself, leaving just enough for services
# that need PrivateTmp before the real bind mount is active.
find "${filesystem}/var" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
install -d -m 1777 "${filesystem}/var/tmp"
install -d -m 0755 "${filesystem}/var/log" "${filesystem}/var/cache" "${filesystem}/var/spool"

# --- Persistent journal (survives slot switches; bind-mounted over the
# per-slot /var/log/journal by an fstab entry in setup.sh) ---
install -d -m 2755 -o root -g systemd-journal "${filesystem}/data/sovereign/log/journal"
install -d -m 0755 "${filesystem}/etc/systemd/journald.conf.d"
cat > "${filesystem}/etc/systemd/journald.conf.d/persistent.conf" <<'EOF'
[Journal]
Storage=persistent
Compress=yes
SystemMaxUse=512M
SystemMaxFileSize=20M
MaxRetentionSec=0
MaxFileSec=0
RuntimeMaxUse=128M
SyncIntervalSec=2m
RateLimitInterval=30s
RateLimitBurst=2000
Seal=yes
EOF
