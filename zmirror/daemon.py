
import queue
from datetime import datetime
import re
import socket
import os
import threading
import json
import traceback

from zmirror.user_commands import handle_command



from . import commands
from .logging import log
from .entities import *
# from .actions import handle_entity_online, handle_entity_offline, handle_entity_present
from .dataclasses import * # , LVMLogicalVolume, VirtualDisk, 
from kpyutils.kiify import to_kd

from . import config as globals





def handle(env):
  cache = None

  log.info("handling event")
  log.info(json.dumps(env, indent=2))

  event_handled = False

  now = datetime.now()
  if "ZEVENT_SUBCLASS" in env:
    zevent = env["ZEVENT_SUBCLASS"]
    log.info(f"handling zfs event: {zevent}")
    zpool = env["ZEVENT_POOL"]

    if zevent == "pool_export":
      log.info(f"zpool {zpool} exported")

      zpool_cache = find_or_create_cache(ZPool, name=zpool)
      handle_disconnected(zpool_cache)

      if zpool in globals.zfs_blockdevs:
        for dev in globals.zfs_blockdevs[zpool].values():
          dev_cache = find_or_create_cache(ZDev, pool=zpool, name=dev.name)
          handle_deactivated(dev_cache)


      event_handled = True
    # zpool event
    elif zevent in ["scrub_finish", "scrub_start", "scrub_abort", "pool_import"]:
      log.info(f"zpool {zpool}: {zevent}")
      zpool_status = config.get_zpool_status(zpool)


      if zevent == "pool_import":
        zpool_cache = find_or_create_cache(ZPool, name=zpool)
        handle_onlined(zpool_cache)


      found_online = False
      if zpool_status is None:
        log.error(f"zpool status failed for pool {zpool}")
      else:
        for match in POOL_DEVICES_REGEX.finditer(zpool_status):
          dev = match.group(1)

          cache = find_or_create_cache(ZDev, pool=zpool, name=dev)
          if match.group(2) == "ONLINE":

            found_online = True
            cache.operation = Since(ZFSOperationState.NONE, now)
            if zevent == "scrub_finish":
              log.info(f"zdev {cache.pool}:{cache.name}: scrubbing finished")
              handle_scrub_finished(cache)
            elif zevent == "scrub_start":
              log.info(f"zdev {cache.pool}:{cache.name}: scrubbing started")
              handle_scrub_started(cache)
            elif zevent == "scrub_abort":
              log.info(f"zdev {cache.pool}:{cache.name}: scrubbing cancelled")
              handle_scrub_aborted(cache)
            elif zevent == "pool_import":
              log.info(f"zdev {cache.pool}:{cache.name}: pool imported, device online")
              handle_onlined(cache)
          
      if found_online is False:
        log.error("likely bug: zpool event but no devices online")
    # TODO: add to docs that the admin must ensure that zpool import
    # uses /dev/mapper (dm) and /dev/vg/lv (lvm) and /dev/disk/by-partlabel (partition)
      # zpool import -d /dev/mapper -d /dev/vg/lv -d /dev/disk/by-partlabel
      # zpool create my-pool mirror /dev/vg-my-vg/my-lv /dev/disk/by-partlabel/my-partition /dev/mapper/my-dm-crypt

    # zpool-vdev event
    elif zevent in ["vdev_online", "statechange"]:
      # possible cases:
        # ZEVENT_POOL:: mypoolname
        # ZEVENT_VDEV_PATH:: /dev/mapper/mypoolname-b-main
        # ZEVENT_VDEV_PATH:: /dev/{vg_bak_gamma/lv_bak_gamma}
        # ZEVENT:: /dev/{sda3}
        # ZEVENT:: /dev/disk/by-partlabel/mypartlabel
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path)
      if zevent == "vdev_online":
        log.info(f"zdev {cache.pool}:{cache.name} went online")
        handle_onlined(cache)
        event_handled = True
      elif zevent == "statechange":
        new_state = env["ZEVENT_VDEV_STATE_STR"]
        if new_state == "OFFLINE":
          log.info(f"zdev {cache.pool}:{cache.name} went offline")
          handle_deactivated(cache)
          event_handled = True
        else:
          log.warning(f"(potential bug) unknown statechange event: { new_state }")
          set_cache_state(cache, EntityState.UNKNOWN)

    # zool-vdev event
    elif zevent in ["resilver_start", "resilver_finish"]:
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path)
      if zevent == "resilver_start":
        handle_resilver_started(cache)
        event_handled = True
      elif zevent == "resilver_finish":
        handle_resilver_finished(cache)

        event_handled = True

  elif "DEVTYPE" in env:
    action = env["ACTION"]
    devtype = env["DEVTYPE"]
    log.info(f"handling udev block event: {action}")


    if action == "add" or action == "remove":
      if devtype == "disk":
        if "ID_PART_TABLE_UUID" in env:
          cache = find_or_create_cache(Disk, uuid=env["ID_PART_TABLE_UUID"])
          log.info(f"{cache.__class__.__name__} {cache.uuid}: {to_kd(cache.state)}")
          udev_event_action(cache, action, now)
          event_handled = True

        # lvm logical volumes
        # these events also have DM_NAME
        #  elif "DM_LV_NAME" in env:
        #  cache = find_or_create_cache(LVMLogicalVolume, \
        #                               vg=env["DM_VG_NAME"], name=env["DM_LV_NAME"])
        #  udev_event_action(cache, action, now)
        #  log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
        #  event_handled = True

        # dm_crypts
        elif "DM_NAME" in env:
          cache = find_or_create_cache(DMCrypt, name=env["DM_NAME"])
          if action == "add":
            handle_onlined(cache)
          else:
            handle_deactivated(cache)
          log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
          event_handled = True

        # virtual device
        elif "DEVPATH" in env and env["DEVPATH"].startswith("/devices/virtual/block/"):
          if env["DEVPATH"].startswith("/devices/virtual/block/zd"):
            devlinks = env["DEVLINKS"].split(" ")
            for devlink in devlinks:
              match = re.match(r'/dev/zvol/(?P<pool>[^/]+)/(?P<volume>.+)$', devlink)
              if match and not re.match(r'-part[0-9]+$', match.group("volume")):
                pool_name = match.group("pool")
                volume_name = match.group("volume")


                cache = find_or_create_cache(ZFSVolume, pool=pool_name, name=volume_name)
                      
                if action == "add":
                  handle_onlined(cache)
                else:
                  handle_deactivated(cache)
                log.info(f"{cache.__class__.__name__} {cache.get_pool()}/{cache.name}: {to_kd(cache.state)}")
                event_handled = True
                break
          # elif "ID_FS_UUID" in env:
          #  cache = find_or_create_cache(VirtualDisk, fs_uuid=env["ID_FS_UUID"])
          #  udev_event_action(cache, action, now)
          #  log.info(f"{cache.__class__.__name__} {cache.fs_uuid}: {to_kd(cache.state)}")
          #  event_handled = True
          else:
            log.warning("need a filesystem uuid or a zvol devlink (if applicable) to identify virtual blockdevices")
        else:
          log.info("nothing to do for disk event")

      elif devtype == "partition":
        cache = find_or_create_cache(Partition, name=env["PARTNAME"])
        udev_event_action(cache, action, now)
        log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
    
    # TODO: figure out what this event actually is.
    elif action == "change" and "DM_ACTIVATION" in env and env["DM_ACTIVATION"] == "1":
      devlinks = env["DEVLINKS"].split(" ")
      for devlink in devlinks:
        match = re.match(r'/dev/mapper/([^/]+)$', devlink)
        if match:
          dm_name = match.group(1)

          cache = find_or_create_cache(DMCrypt, name=dm_name)
          handle_onlined(cache)
          log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
          event_handled = True

          break
    if not event_handled:
      log.warning("event not handled by zmirror")






def udev_event_action(entity, action, now):
  if action == "add":
    handle_appeared(entity)
  elif action == "remove":
    handle_disconnected(entity)



def handle_client(con: socket.socket, client_address, event_queue: queue.Queue):
  with con:
    try:
      log.info(f"handling connection to zmirror socket")


      # Read until ':' to get the length
      length_str = ""
      while True:
          char = con.recv(1).decode('utf-8')
          if char == ':':
              break
          length_str += char

      # Convert length to integer
      total_length = int(length_str)

      # Read the JSON data of the specified length
      data = b""
      while len(data) < total_length:
          more_data = con.recv(total_length - len(data))
          if not more_data:
              raise ConnectionError("Connection closed before receiving all data")
          data += more_data

      message = data.decode('utf-8')
      event = json.loads(message)
      if "ZMIRROR_COMMAND" in event:
        with con.makefile('w') as stream:
          handle_command(event["ZMIRROR_COMMAND"], stream)
          stream.flush()
      else:
        event_queue.put(event)
    except Exception as ex:
      log.error("communication error: %s", ex)



def handle_event(event_queue: queue.Queue):
  while True:
    event = event_queue.get()
    try:
      handle(event)
      commands.execute_commands()
    except Exception as ex:
      log.error(f"failed to handle event: {str(event)}")
      log.error(f"Exception : {traceback.format_exc()} --- {str(ex)}")
    finally:
      if event_queue.empty():
        save_cache()


# starts a daemon, or rather a service, or maybe it should be called simply a server,
# a listening loop that listens to whatever is being sent on a
# unix socket: /var/run/zmirror/zmirror.socket, to which
# zmirror-udev and zmirror-zed send their event streams.
# these scripts connect to it, send a set of environment variables and then disconnect.
# this service then reads those environment variables
# and creates event objects
# inside a list that is thread safe (only one thread ever changes the list)

# on the other side, in a different thread (another loop)
# this daemon simply removes the events from the list in order (FIFO)
#
# the code for this should be largely will lay in zmirror-handler.py:
# and handles the events
# and by handling we mean for now, that they simply get logged
# so this is just a description for the next milestone
def daemon(args):# pylint: disable=unused-argument

  config.is_daemon = True


  socket_path = args.socket_path
  # Define the path for the Unix socket

  # Make sure the socket does not already exist
  try:
    os.unlink(socket_path)
  except OSError:
    if os.path.exists(socket_path):
      raise

  # Create a UDS (Unix Domain Socket)
  server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

  os.makedirs(os.path.dirname(socket_path), exist_ok=True)

  # Bind the socket to the path
  server.bind(socket_path)

  # Listen for incoming connections
  server.listen()

  log.info(f"listening on {socket_path}")


  event_queue = queue.Queue()



  # Create a thread-safe list
  handle_event_thread = threading.Thread(target=handle_event, args=(event_queue, ))
  handle_event_thread.start()
  # TODO: closing the handle event thread is not implemented


  # we load the config after we have started the server, so that we cannot miss any events that might change the config while it is being loaded
  init_config(cache_path=args.cache_path, config_path=args.config_path)

  try:
    while True:
      # Wait for a connection
      connection, client_address = server.accept()
      # Start a new thread for the connection
      client_thread = threading.Thread(target=handle_client, args=(connection, client_address, event_queue))
      client_thread.start()
  except KeyboardInterrupt:
    log.info("Keyboard Interrupt.")
  except Exception as exception:
    log.error(str(exception))
  finally:
    server.close()
    os.unlink(socket_path)
    log.info("Server gracefully shut down")
    try:
      os.remove(socket_path)
    except Exception as exception:
      log.warning(exception)
