#!/bin/bash

# this file must be put into /etc/zfs/zed.d/
# the `all-` prefix is necessary and it seems so is the `.sh` suffix
# the zmirror-trigger script must be in the PATH (on debian based systems it will be installed in /usr/local/bin)

[ -f "''${ZED_ZEDLET_DIR}/zed.rc" ] && . "''${ZED_ZEDLET_DIR}/zed.rc"
  . "''${ZED_ZEDLET_DIR}/zed-functions.sh"
        
zed_log_msg zmirror running

zmirror-trigger