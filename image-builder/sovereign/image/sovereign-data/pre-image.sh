#!/bin/bash

set -eu

filesystem=$1
genimage_input=$2

source "${IGconf_image_outputdir}/img_uuids"

install -d -m 0755 "${filesystem}/data/sovereign"

MKE2FS_ROOT="-U $ROOT_UUID ${IGconf_fs_ext4_mkfs_args:-}"
MKE2FS_DATA="${IGconf_fs_ext4_mkfs_args:-}"
VFAT_ARGS="-S $IGconf_device_sector_size -i $BOOT_LABEL ${IGconf_fs_vfat_mkfs_args:-}"

sed \
  -e "s|<IMAGE_NAME>|$IGconf_image_name|g" \
  -e "s|<IMAGE_SUFFIX>|$IGconf_image_suffix|g" \
  -e "s|<BOOT_SIZE>|$IGconf_image_boot_part_size|g" \
  -e "s|<ROOT_SIZE>|$IGconf_image_root_part_size|g" \
  -e "s|<DATA_SIZE>|$IGconf_image_data_part_size|g" \
  -e "s|<SETUP>|'$(readlink -ef setup.sh)'|g" \
  -e "s|<MKE2FS_CONF>|'$(readlink -ef mke2fs.conf)'|g" \
  -e "s|<MKE2FS_ROOT>|$MKE2FS_ROOT|g" \
  -e "s|<MKE2FS_DATA>|$MKE2FS_DATA|g" \
  -e "s|<VFAT_ARGS>|$VFAT_ARGS|g" \
  genimage.cfg.in > "${genimage_input}/genimage.cfg"

