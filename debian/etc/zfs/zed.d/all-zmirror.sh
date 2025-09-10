#!/bin/bash

# this file must be put into /etc/zfs/zed.d/
# the `all-` prefix is necessary and it seems so is the `.sh` suffix

[ -f "''${ZED_ZEDLET_DIR}/zed.rc" ] && . "''${ZED_ZEDLET_DIR}/zed.rc"
  . "''${ZED_ZEDLET_DIR}/zed-functions.sh"

/usr/local/bin/zmirror-trigger