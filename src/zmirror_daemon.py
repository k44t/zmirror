
import queue
from datetime import datetime
import re
import socket
import os
import threading
import json
import traceback
import zmirror_commands
from zmirror_logging import log
from zmirror_utils import load_cache, save_cache, load_config, find_or_create_zfs_cache_by_vdev_path,  load_config_for_cache
import zmirror_utils as core
from zmirror_actions import handle_entity_online, handle_entity_offline
from pyutils import find_or_create_cache
from zmirror_dataclasses import ZFSBackingBlockDeviceCache, ZFSOperationState, EntityState, Disk, LVMLogicalVolume, DMCrypt, VirtualDisk, Partition, Since, ZFSVolume, ZPool, set_entity_state
from ki_utils import to_kd

import zmirror_globals as globals




def handle(env):
  cache_dictionary = core.cache_dict
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
      log.info(f"zpool {cache.pool} exported")

      zpool_cache = find_or_create_cache(cache_dictionary, ZPool, name=zpool)
      handle_entity_offline(zpool_cache, now)

      if zpool in globals.zfs_blockdevs:
        for dev in globals.zfs_blockdevs[zpool]:
          dev_cache = find_or_create_cache(cache_dictionary, ZFSBackingBlockDeviceCache, pool=zpool, dev=dev)
          handle_entity_offline(dev_cache, now)


      event_handled = True
    # zpool event
    elif zevent in ["scrub_finish", "scrub_start", "scrub_abort", "pool_import"]:
      log.info(f"zpool {zpool}: {zevent}")
      zpool_status = core.get_zpool_status(zpool)

      regex = re.compile(r'^ {12}([-a-zA-Z0-9_]+) +(ONLINE) +[0-9]+ +[0-9]+ +[0-9]+ *.*$', \
                         re.MULTILINE)

      if zevent == "pool_import":
        zpool_cache = find_or_create_cache(cache_dictionary, ZPool, name=zpool)
        handle_entity_online(zpool_cache, now)
      found = False
      for match in regex.finditer(zpool_status):
        found = True
        dev = match.group(1)

        cache = find_or_create_cache(cache_dictionary, ZFSBackingBlockDeviceCache, pool=zpool, dev=dev)
        cache.operation = Since(ZFSOperationState.NONE, now)
        if zevent == "scrub_finish":
          log.info(f"zdev {cache.pool}:{cache.dev}: scrubbing finished")
          cache.last_scrubbed = now


          config = load_config_for_cache(cache)
          if hasattr(config, "handle_scrubbed"):
            config.handle_scrubbed()

          event_handled = True
        elif zevent == "scrub_start":
          log.info(f"zdev {cache.pool}:{cache.dev}: scrubbing started")
          cache.operation.what = ZFSOperationState.SCRUBBING
          event_handled = True
        elif zevent == "scrub_abort":
          log.info(f"zdev {cache.pool}:{cache.dev}: scrubbing cancelled")
          cache.operation.what = ZFSOperationState.NONE
          event_handled = True
        elif zevent == "pool_import":
          log.info(f"zdev {cache.pool}:{cache.dev}: pool imported, device online")
          handle_entity_online(cache, now)
          event_handled = True
      if found is False:
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
      cache = find_or_create_zfs_cache_by_vdev_path(cache_dictionary, zpool, vdev_path)
      if zevent == "vdev_online":
        log.info(f"zdev {cache.pool}:{cache.dev} went online")
        handle_entity_online(cache, now)
        event_handled = True
      elif zevent == "statechange":
        new_state = env["ZEVENT_VDEV_STATE_STR"]
        if new_state == "OFFLINE":
          log.info(f"zdev {cache.pool}:{cache.dev} went offline")
          handle_entity_offline(cache, now)
          event_handled = True
        else:
          log.warning(f"(potential bug) unknown statechange event: { new_state }")
          set_entity_state(cache, EntityState.UNKNOWN)

    # zool-vdev event
    elif zevent in ["resilver_start", "resilver_finish"]:
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(cache_dictionary, zpool, vdev_path)
      cache.operation = Since(ZFSOperationState.NONE, now)
      if zevent == "resilver_start":
        cache.operation = Since(ZFSOperationState.RESILVERING, now)
        event_handled = True
      elif zevent == "resilver_finish":
        cache.operation = Since(ZFSOperationState.NONE, now)
        cache.last_resilvered = now

        config = load_config_for_cache(cache)
        if hasattr(config, "handle_resilvered"):
          config.handle_resilvered()

        event_handled = True

  elif "DEVTYPE" in env:
    action = env["ACTION"]
    devtype = env["DEVTYPE"]
    log.info(f"handling udev block event: {action}")

    if action == "add" or action == "remove":
      if devtype == "disk":
        if "ID_SERIAL" in env:
          cache = find_or_create_cache(cache_dictionary, Disk, serial=env["ID_SERIAL"], create_args={"devpath": env["DEVNAME"]})
          udev_event_action(cache, action, now)
          log.info(f"{cache.__class__.__name__} {cache.serial}: {to_kd(cache.state)}")
          event_handled = True

        # lvm logical volumes
        # these events also have DM_NAME
        elif "DM_LV_NAME" in env:
          cache = find_or_create_cache(cache_dictionary, LVMLogicalVolume, \
                                       vg=env["DM_VG_NAME"], name=env["DM_LV_NAME"])
          udev_event_action(cache, action, now)
          log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
          event_handled = True
        # dm_crypts
        elif "DM_NAME" in env:
          cache = find_or_create_cache(cache_dictionary, DMCrypt, name=env["DM_NAME"])
          udev_event_action(cache, action, now)
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


                cache = find_or_create_cache(cache_dictionary, ZFSVolume, pool=pool_name, name=volume_name)
                udev_event_action(cache, action, now)
                log.info(f"{cache.__class__.__name__} {cache.get_pool()}/{cache.name}: {to_kd(cache.state)}")
                event_handled = True
                break
          elif "ID_FS_UUID" in env:
            cache = find_or_create_cache(cache_dictionary, VirtualDisk, fs_uuid=env["ID_FS_UUID"], create_args={"devpath": env["DEVNAME"]})
            udev_event_action(cache, action, now)
            log.info(f"{cache.__class__.__name__} {cache.fs_uuid}: {to_kd(cache.state)}")
            event_handled = True
          else:
            log.warning("need a filesystem uuid or a zvol devlink (if applicable) to identify virtual blockdevices")
        else:
          log.info("nothing to do for disk event")

      elif devtype == "partition":
        cache = find_or_create_cache(cache_dictionary, Partition, name=env["PARTNAME"], create_args={"devpath": env["DEVNAME"]})
        udev_event_action(cache, action, now)
        log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
    elif action == "change" and "DM_ACTIVATION" in env and env["DM_ACTIVATION"] == "1":
      devlinks = env["DEVLINKS"].split(" ")
      for devlink in devlinks:
        match = re.match(r'/dev/mapper/([^/]+)$', devlink)
        if match:
          dm_name = match.group(1)


          cache = find_or_create_cache(cache_dictionary, DMCrypt, name=dm_name)
          handle_entity_online(cache, now)
          log.info(f"{cache.__class__.__name__} {cache.name}: {to_kd(cache.state)}")
          event_handled = True

          break
    zmirror_commands.execute_commands()
    if not event_handled:
      log.warning("event not handled by zmirror")






def udev_event_action(entity, action, now):
  if action == "add":
    handle_entity_online(entity, now)
  elif action == "remove":
    handle_entity_offline(entity, now)



def handle_client(connection: socket.socket, client_address, event_queue: queue.Queue):
  try:
    log.info(f"handling client connection to client_address {client_address}")

    data = bytearray(b'')
    while True:
      buf = connection.recv(16)
      if buf != b'':
        data.extend(buf)
      else:
        break
    message = data.decode('utf-8')
    event = json.loads(message)
    event_queue.put(event)
  except Exception as ex:
    log.error("error while receiving data from zmirror-trigger: %s", ex)
  finally:
    # Clean up the connection
    connection.close()



def handle_event(event_queue: queue.Queue):
  while True:
    event = event_queue.get()
    try:
      handle(event)
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

  load_cache()
  load_config()


  # Define the path for the Unix socket
  socket_path = "/var/run/zmirror/zmirror_service.socket"

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
