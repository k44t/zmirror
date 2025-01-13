



import os, stat, os.path
import shutil
import re
import time
import subprocess
import json
from natsort import natsorted
from datetime import datetime, timedelta
import logging
import os




log = logging.getLogger(__name__)


def convert_dict_to_strutex(dictionary):
    result_string = "env"
    for key, value in dictionary.items():
        result_string = result_string + f"\n\t{key}:: {value}"
    return result_string

def main():
    logfile = '/var/run/zmirror/log.st'
    parent_directory = os.path.dirname(logfile)
    os.makedirs(parent_directory, exist_ok = True)
    logging.basicConfig(filename=logfile, 
                        level=logging.INFO, 
                        format='%(asctime)s %(levelname)-8s %(message)s',    
                        datefmt='%Y-%m-%d %H:%M:%S')
    log.info("starting zmirror")
    all_env_vars = dict(os.environ)
    new_all_env_vars = dict()
    for key, value in all_env_vars.items():
        if key[0] != "_":
            new_all_env_vars[key] = value
    log.info(f"environment variables: {convert_dict_to_strutex(new_all_env_vars)}")
    
if __name__ == "__main__":
    main()


"""

# use the binary from the env variable ZPOOL when available or use zpool from PATH (which is available in udev)

udev block
    remove
        disk
            match
                DEVTYPE: disk

                ID_USB_VENDOR_ID
                ID_USB_MODEL_ID
                ID_PART_TABLE_UUID
            
            reaction
                partprobe???

        partition
            match
                DEVTYPE: partition
                PARTNAME
                
                ID_FS_UUID
                ID_PART_ENTRY_UUID


            reaction
                
                zpool offline ...
                # we ignore generated zevents

                cryptsetup close ...
        virtual disk (decrypted blockdev) or virtual partition
            match
                see disk
            reaction
                zpool online ...
    add
        partition
            match
                # ACTION: add
                DEVTYPE: partition

                PARTNAME: eva-b-main

                ID_FS_UUID: 5734e13f-6732-4c68-bc14-22249afaac17

                # this is the one in /dev/disk/by-partuuid
                ID_PART_ENTRY_UUID: 57507cd3-dc80-46c5-b93b-ab51dc41ad37
            
            reaction
                
                cryptsetup open
                # will trigger next event
        
zed
    # irrelevant, but useful to know how to ignore
    history
        ZEVENT_CLASS:: sysevent.fs.zfs.history_event
        ZEVENT_POOL_GUID:: 0xD842CE6598FB0398
    # irrelevant
    scrub start
        match
            ZEVENT_CLASS: sysevent.fs.zfs.scrub_start
    
    ? scrub completed
        if configured
            zpool offline
            if configured
                cryptsetup close
        



    resilver finished
        match
            ZEVENT_CLASS: sysevent.fs.zfs.resilver_finish
            ZEVENT_SUBCLASS: resilver_finish

        reaction
            if now falls into scrub interval
                start scrub
            else
                see scrub completed
            



"""