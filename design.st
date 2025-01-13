
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
            