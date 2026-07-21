#!/bin/bash

set -eu

case "$1" in
  ROOT)
    root_uuid=$2
    boot_uuid=$3
    cat > "$IMAGEMOUNTPATH/etc/fstab" <<EOF
UUID=$root_uuid / ext4 rw,relatime,errors=remount-ro,commit=30 0 1
UUID=$boot_uuid /boot/firmware vfat defaults,rw,noatime,errors=remount-ro 0 2
/dev/disk/by-label/DATA /data ext4 defaults,rw,noatime 0 2
EOF
    ;;
  BOOT)
    root_uuid=$2
    sed -i.bak "s|root=[^ ]*|root=UUID=$root_uuid|" "$IMAGEMOUNTPATH/cmdline.txt"
    rm -f "$IMAGEMOUNTPATH/cmdline.txt.bak"
    ;;
esac
