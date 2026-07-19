#!/bin/bash

set -eu

case "$1" in
  ROOT)
    cat > "$IMAGEMOUNTPATH/etc/fstab" <<'EOF'
/dev/disk/by-slot/system / ext4 rw,relatime,errors=remount-ro,commit=30 0 1
/dev/disk/by-slot/boot /boot/firmware vfat defaults,rw,noatime,errors=remount-ro 0 2
/dev/disk/by-label/DATA /data ext4 defaults,rw,noatime 0 2
EOF
    ;;
  BOOT)
    sed -i 's|root=\([^ ]*\)|root=/dev/disk/by-slot/system|' "$IMAGEMOUNTPATH/cmdline.txt"
    ;;
esac

