# enable logging of the environment variables for all relevant events
log-env: yes


dm-crypt

    eva-a-main: partition 
        partprobe: no
        key-command: cat /dev/disk/by-partlabel/eva-key
        
        
        uuid
        name

        match
            ID_USB_MODEL_ID...

    eva-b-main: disk
        partprobe: yes
        key-command: ...
        
        usb-vendor: 1aeb
        usb-model: 00bx

        # seems to be unique
        id-serial: TOSHIBA_MG09ACA18TE_71L0A33JFQDH
        id-serial-short: 71L0A33JFQDH

        udev
            USB_MODEL_ID
            ID_USB_MODEL_ID


#   dm-mirror
        eva-c-main
            partition
                name: eva-x-main
            disk
                udev
                    USB_MODEL_ID


zfs
    eva
        eva-a-main: partition
            name: eva-a-main
            uuid: ...
                
            udev
                # id-usb_MODEL ID --> ID_USB_MODEL_ID
                FS_UUID: ...
                

        eva-b-main: dm-crypt

            # DM_NAME
            name: 
            
            # DM_UUID
            uuid: 
            
            udev
                FS_UUID: ...
                
            

