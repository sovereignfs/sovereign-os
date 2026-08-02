#!/bin/bash

set -eu

case "$1" in
  ROOT)
    cat > "$IMAGEMOUNTPATH/etc/fstab" <<'EOF'
/dev/disk/by-slot/active/system  /               ext4  ro,relatime,commit=30            0  1
/dev/disk/by-slot/active/boot    /boot/firmware  vfat  ro,noatime,nofail                0  2
/dev/disk/by-slot/bootconfig     /bootfs         vfat  rw,noatime,nofail                0  2
/dev/disk/by-label/DATA          /data           ext4  defaults,rw,noatime              0  2

# /var is per-slot and mounted by sovereign-slot-var-generator, not
# listed here (its source path depends on which slot is currently
# active, which a static fstab line can't express).

# Appliance releases (RFC-0014) live on /data, independent of base-OS
# slot switches (RFC-0016) -- bind-mounted back over the empty /opt/sovereign
# mount point every already-qualified piece of code still references unchanged.
/data/sovereign/releases         /opt/sovereign  none  bind,x-systemd.requires-mounts-for=/data                          0  0

# Journal persists across slot switches even though /var itself is
# per-slot -- mounted after var.mount so it lands inside the real /var,
# not the reclaimed skeleton that briefly exists before var.mount runs.
/data/sovereign/log/journal      /var/log/journal  none  bind,x-systemd.requires-mounts-for=/data,x-systemd.after=var.mount  0  0

# /etc's own persistence is handled by etc.mount (an
# overlayfs, not a plain bind mount -- passwd/usermod/PAM write account
# files via a sibling-temp-file-then-rename in the SAME directory, which
# needs the whole directory writable, not just the individual file).
#
# /home persists across slot switches for the same two reasons as /etc:
# imager-provisioned SSH authorized_keys must survive a base-OS update,
# not revert to build-time (empty) defaults.
/data/sovereign/identity/home       /home           none  bind,x-systemd.requires-mounts-for=/data  0  0
EOF
    ;;
  BOOT)
    sed -i.bak "s|root=[^ ]*|root=/dev/disk/by-slot/active/system|" "$IMAGEMOUNTPATH/cmdline.txt"
    rm -f "$IMAGEMOUNTPATH/cmdline.txt.bak"
    ;;
esac
