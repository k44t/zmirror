#!/bin/bash

# Extract the RAID name from UDISKS_MD_NAME
RAID_NAME=$(echo "$UDISKS_MD_NAME" | cut -d':' -f2)
[ -z "$RAID_NAME" ] && { echo "Error: RAID name is empty."; exit 1; } || echo "$RAID_NAME"