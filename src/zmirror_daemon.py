from datetime import datetime
import re
import socket
import os
import threading
import json
from zmirror_logging import log
from zmirror_utils import *
import zmirror_utils as core
import queue




def handle(env):
  cache_dict = core.cache_dict

  log.info("handling udev and zfs events by interpreting environment variables")

  now = datetime.now()
  if "ZEVENT_SUBCLASS" in env:
    zevent = env["ZEVENT_SUBCLASS"]
    log.info(f"handling zfs event: {zevent}")
    zpool = env["ZEVENT_POOL"]

    # zpool event
    if zevent in ["scrub_finish", "scrub_start"]:
      zpool_status = core.get_zpool_status(zpool)

      regex = re.compile(rf'^\s+([a-zA-Z0-9_]+)\s+(ONLINE)\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$')

      for match in regex.finditer(zpool_status):
        dev = match.group(1)

        cache = find_or_create_cache(cache_dict, ZFS_Blockdev_Cache, pool=zpool, dev=dev)
        cache.operation = Since(ZFS_Operation_State.NONE, now)
        if zevent == "scrub_finish":
          cache.last_scrubbed = now
        elif zevent == "scrub_start":
          cache.operation.state = ZFS_Operation_State.SCRUBBING
    # TODO: add to docs that the admin must ensure that zpool import uses /dev/mapper (dm) and /dev/vg/lv (lvm) and /dev/disk/by-partlabel (partition)
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
      cache = find_or_create_zfs_cache_by_vdev_path(cache_dict, zpool, vdev_path)
      if zevent == "vdev_online":
        log.info(f"zdev {cache.pool}:{cache.dev} went online")
        cache.state = Since(Entity_State.ONLINE, now)
      elif zevent == "statechange":
        new_state = env["ZEVENT_VDEV_STATE_STR"]
        if new_state == "OFFLINE":
          log.info(f"zdev {cache.pool}:{cache.dev} went offline")
          cache.state = Since(Entity_State.DISCONNECTED, now)
        else:
          log.warning(f"(potential bug) unknown statechange event: { new_state }")
          cache.state = Since(Entity_State.UNKNOWN, now)

    # zool-vdev event
    elif zevent in ["resilver_start", "resilver_finish"]:
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(vdev_path)
      cache.operation = Since(ZFS_Operation_State.NONE, now)
      if zevent == "resilver_start":
        cache.operation = Since(ZFS_Operation_State.RESILVERING, now)
      elif zevent == "resilver_finish":
        cache.operation = Since(ZFS_Operation_State.NONE, now)
        cache.last_resilvered = now

  elif ("DEVTYPE" in env):
    action = env["ACTION"]
    devtype = env["DEVTYPE"]
    log.info(f"handling udev block event: {action}")
    if devtype == "disk":
      if "ID_SERIAL" in env:
        cache = find_or_create_cache(cache_dict, Disk, serial=env["ID_SERIAL"])
      elif "DM_NAME" in env:
        cache = find_or_create_cache(cache_dict, DM_Crypt, name=env["DM_NAME"])
    elif devtype == "partition":
      cache = find_or_create_cache(cache_dict, Partition, name=env["PARTNAME"])
    if cache != None:
      if action == "add":
        cache.state = Since(Entity_State.ONLINE, now)
      elif action == "remove":
        cache.state = Since(Entity_State.DISCONNECTED, now)

  log.info("finished handling zmirror event.")




def handle_client(connection: socket.socket, client_address, event_queue: queue.Queue):
  try:
    log.info(f"Connection from {client_address}")

    data = bytearray(b'')
    while True:
      buf = connection.recv(16)
      if buf != b'':
        data.extend(buf)
      else:
        break
    message = data.decode('utf-8')
    event = json.reads(message)
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
      log.error("failed to handle event: ", event)
      log.error("Exception: ", ex)
    finally:
      if event_queue.empty():
        save_cache()


# starts a daemon, or rather a service, or maybe it should be called simply a server, a listening loop that listens to whatever is being sent on a unix socket: /var/run/zmirror/zmirror.socket, to which zmirror-udev and zmirror-zed send their event streams. 
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
def daemon(args):
  global cache_dict

  cache_dict = load_yaml_cache(cache_file_path)

  # Define the path for the Unix socket
  socket_path = "/tmp/zmirror_service.socket"

  # Make sure the socket does not already exist
  try:
    os.unlink(socket_path)
  except OSError:
    if os.path.exists(socket_path):
      raise

  # Create a UDS (Unix Domain Socket)
  server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

  # Bind the socket to the path
  server.bind(socket_path)

  # Listen for incoming connections
  server.listen()

  log.info(f"listening on {socket_path}")


  event_queue = queue.Queue()
    

  # Create a thread-safe list
  handle_event_thread = threading.Thread(target=handle_event, args=(event_queue, ))
  handle_event_thread.start()

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
    os.remove(socket_path)




