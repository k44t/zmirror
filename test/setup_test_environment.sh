#!/usr/bin/env bash
set -xe

# does folder exist?
mkdir -p /tmp/zmirror






# setting up the test environment
## create blockdevs for backing the zpool zmirror-sysfs
### creates zmirror
# $1 = the blockdev created by: zfs create eva/zmirror -V 10G


blockdev=$1
mkdir -p /tmp/zmirror
zpool create zmirror -R /tmp/zmirror/zmirror $blockdev -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f


### creates blockdevs that will be a mirror in zpool zmirror-sysfs
zfs create zmirror/sysfs-a -V 100MiB
zfs create zmirror/sysfs-b -V 100MiB
zfs create zmirror/sysfs-s -V 100MiB

zfs create zmirror/big-a -V 200MiB
zfs create zmirror/big-b -V 200MiB

zfs create zmirror/bak-a -V 800MiB
zfs create zmirror/bak-b-alpha -V 800MiB
zfs create zmirror/bak-b-beta -V 800MiB



## partition the blockdevs

parted /dev/zvol/zmirror/sysfs-a -- mklabel gpt
parted /dev/zvol/zmirror/sysfs-a -- mkpart zmirror-sysfs-a 1MiB 100%

parted /dev/zvol/zmirror/sysfs-b -- mklabel gpt
parted /dev/zvol/zmirror/sysfs-b -- mkpart zmirror-sysfs-b 1MiB 100%

parted /dev/zvol/zmirror/sysfs-s -- mklabel gpt
parted /dev/zvol/zmirror/sysfs-s -- mkpart zmirror-sysfs-s 1MiB 100%

parted /dev/zvol/zmirror/big-a -- mklabel gpt
parted /dev/zvol/zmirror/big-a -- mkpart zmirror-big-a 1MiB 100%

parted /dev/zvol/zmirror/big-b -- mklabel gpt
parted /dev/zvol/zmirror/big-b -- mkpart zmirror-big-b 1MiB 100%

parted /dev/zvol/zmirror/bak-a -- mklabel gpt
parted /dev/zvol/zmirror/bak-a -- mkpart zmirror-bak-a 1MiB 100%

parted /dev/zvol/zmirror/bak-b-alpha -- mklabel gpt
parted /dev/zvol/zmirror/bak-b-alpha -- mkpart zmirror-bak-b-alpha 1MiB 100%

parted /dev/zvol/zmirror/bak-b-beta -- mklabel gpt
parted /dev/zvol/zmirror/bak-b-beta -- mkpart zmirror-bak-b-beta 1MiB 100%


udevadm settle


## create encryptions via cryptsetup
# (remember to provide the zmirror-key file into the current folder!)

cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-sysfs-a --key-file ./zmirror-key --batch-mode
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-sysfs-b --key-file ./zmirror-key --batch-mode
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-sysfs-s --key-file ./zmirror-key --batch-mode

cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-big-a --key-file ./zmirror-key --batch-mode
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-big-b --key-file ./zmirror-key --batch-mode

cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-bak-a --key-file ./zmirror-key --batch-mode

cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-bak-b-alpha --key-file ./zmirror-key --batch-mode
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-bak-b-beta --key-file ./zmirror-key --batch-mode


## open encrypted disks

cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-a zmirror-sysfs-a --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-b zmirror-sysfs-b --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./zmirror-key

cryptsetup open /dev/disk/by-partlabel/zmirror-big-b zmirror-big-b --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-big-a zmirror-big-a --key-file ./zmirror-key

cryptsetup open /dev/disk/by-partlabel/zmirror-bak-a zmirror-bak-a --key-file ./zmirror-key

cryptsetup open /dev/disk/by-partlabel/zmirror-bak-b-alpha zmirror-bak-b-alpha --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-bak-b-beta zmirror-bak-b-beta --key-file ./zmirror-key



## create zmirror-bak zpools

zpool create zmirror-bak-a -R /tmp/zmirror/zmirror-bak-a /dev/mapper/zmirror-bak-a -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f

zpool create zmirror-bak-b -R /tmp/zmirror/zmirror-bak-b mirror /dev/mapper/zmirror-bak-b-alpha /dev/mapper/zmirror-bak-b-beta -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f


### creates blockdevs on the bak disk
zfs create zmirror-bak-a/sysfs -V 100MiB

zfs create zmirror-bak-a/big -V 200MiB

zfs create zmirror-bak-b/sysfs -V 100MiB

zfs create zmirror-bak-b/big -V 200MiB


### create zpools
zpool create zmirror-sysfs -R /tmp/zmirror/zmirror-sysfs mirror /dev/mapper/zmirror-sysfs-a /dev/mapper/zmirror-sysfs-b /dev/mapper/zmirror-sysfs-s /dev/zvol/zmirror-bak-a/sysfs /dev/zvol/zmirror-bak-b/sysfs -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f

zpool create zmirror-big -R /tmp/zmirror/zmirror-big mirror /dev/mapper/zmirror-big-a /dev/mapper/zmirror-big-b /dev/mapper/zmirror-sysfs-s /dev/zvol/zmirror-bak-a/big /dev/zvol/zmirror-bak-b/big -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f