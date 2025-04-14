#!/bin/bash

PARENT=$(echo "$DEVPATH" | sed -E 's:(^/devices/virtual/block/(.+)/(.+)|.+)$:\2:g')

[ -z "$PARENT" ] && { echo "Error: parent device name not found."; exit 1; }

RAID_NAME=$(udevadm info --query=property /dev/$PARENT | grep -E '^ZMIRROR_MD_NAME=' | sed -E 's/^[^=]+=//g')

[ -z "$RAID_NAME" ] && { echo "Error: RAID name is empty."; exit 1; }

PART_NUM=$(echo "$DEVPATH" | sed -E 's|/devices/virtual/block/md[0-9]+/md[0-9]+p([0-9]+)$|\1|g')

echo "$RAID_NAME$PART_NUM"