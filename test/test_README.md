# show list of zfs

zfs list

# take dev online

zpool online test-sysfs test-sysfs-b

# import zpool

zpool import test-bak-delta -R /tmp/zmirror/test-bak-delta

## no such pool?

does folder exist?
mkdir /tmp/zmirror






# setting up the test environment
## create blockdevs for backing the zpool zmirror-sysfs
### creates zmirror
$1 = the blockdev created by: zfs create eva/zmirror -V 10G

```
blockdev=$1
mkdir -p /tmp/zmirror
zpool create zmirror -R /tmp/zmirror/zmirror $blockdev -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f
```

### creates blockdevs that will be a mirror in zpool zmirror-sysfs
```
zfs create zmirror/sysfs-a -V 1G
zfs create zmirror/sysfs-b -V 1G
zfs create zmirror/big-a -V 2G
zfs create zmirror/big-b -V 2G
zfs create zmirror/bak-lvm-vg -V 4G
zfs create zmirror/bak-zpool -V 4G
```

```
zfs create zmirror/bak-zpool -V 4G
```

## partition the blockdevs
```
parted /dev/zvol/zmirror/sysfs-a -- mklabel gpt
parted /dev/zvol/zmirror/sysfs-a -- mkpart zmirror-sysfs-a 1M 100%

parted /dev/zvol/zmirror/sysfs-b -- mklabel gpt
parted /dev/zvol/zmirror/sysfs-b -- mkpart zmirror-sysfs-b 1M 100%

parted /dev/zvol/zmirror/big-a -- mklabel gpt
parted /dev/zvol/zmirror/big-a -- mkpart zmirror-big-a 1M 100%

parted /dev/zvol/zmirror/big-b -- mklabel gpt
parted /dev/zvol/zmirror/big-b -- mkpart zmirror-big-b 1M 100%

parted /dev/zvol/zmirror/bak-lvm-vg -- mklabel gpt
parted /dev/zvol/zmirror/bak-lvm-vg -- mkpart zmirror-bak-lvm-vg 1M 100%

parted /dev/zvol/zmirror/bak-zpool -- mklabel gpt
parted /dev/zvol/zmirror/bak-zpool -- mkpart zmirror-bak-zpool 1M 100%
```


## create encryptions via cryptsetup
(remember to provide the zmirror-key file into the current folder!)
```
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-bak-lvm-vg --key-file ./zmirror-key
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-bak-zpool --key-file ./zmirror-key
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-sysfs-a --key-file ./zmirror-key
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-sysfs-b --key-file ./zmirror-key
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-big-a --key-file ./zmirror-key
cryptsetup luksFormat /dev/disk/by-partlabel/zmirror-big-b --key-file ./zmirror-key
```

## open encrypted disks
```
cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-a zmirror-sysfs-a --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-b zmirror-sysfs-b --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-big-b zmirror-big-b --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-big-a zmirror-big-a --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-bak-lvm-vg zmirror-bak-lvm-vg --key-file ./zmirror-key
cryptsetup open /dev/disk/by-partlabel/zmirror-bak-zpool zmirror-bak-zpool --key-file ./zmirror-key
```

## partitioning
```
parted /dev/mapper/zmirror-bak-lvm-vg -- mklabel gpt
parted /dev/mapper/zmirror-bak-lvm-vg -- mkpart zmirror-bak-lvm-vg-1 1M 33%
parted /dev/mapper/zmirror-bak-lvm-vg -- mkpart zmirror-bak-lvm-vg-2 33% 66%
parted /dev/mapper/zmirror-bak-lvm-vg -- mkpart zmirror-bak-lvm-vg-3 66% 100%
```

## create raid with 3 devices
```
mdadm --create --verbose /dev/md0 --level=5 --raid-devices=3 /dev/disk/by-partlabel/zmirror-bak-lvm-vg-1 /dev/disk/by-partlabel/zmirror-bak-lvm-vg-2 /dev/disk/by-partlabel/zmirror-bak-lvm-vg-3
```

## create zmirror-bak-lvm-vg
pvcreate /dev/mapper/zmirror-bak-lvm-vg --uuid 0fyBQa-FUgx-EHGn-vBGB-b2JT-Sgrx-wTtjT7
vgcreate vg-zmirror-bak-lvm-vg /dev/mapper/zmirror-bak-lvm-vg
lvcreate -n zmirror-sysfs --size 1G vg-zmirror-bak-lvm-vg
lvcreate -n zmirror-big --size 2G vg-zmirror-bak-lvm-vg


## create zmirror-bak-zpool
```
zpool create zmirror-bak-zpool -R /tmp/zmirror/zmirror-bak-zpool /dev/mapper/zmirror-bak-zpool -o autotrim=on -O acltype=posix -O atime=off -O canmount=off -O dnodesize=auto -O utf8only=on -O xattr=sa -O mountpoint=none -f
```


### creates blockdevs for zmirror-bak-beta
```
zfs create zmirror-bak-alpha/big-b -V 2G
```