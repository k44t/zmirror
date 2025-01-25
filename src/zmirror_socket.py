from datetime import datetime
import re
import socket
import os
import threading
import json
from zmirror_logging import log
from zmirror_utils import *






def handle(env = None):
  global cache_dict
  cache_dict = load_yaml_cache()
  log.info("handling udev and zfs events by interpreting environment variables")
  if env == None:
    env = dict(os.environ)

  now = datetime.now()
  if "ZEVENT_CLASS" in env:
    zevent = env["ZEVENT_SUBCLASS"]
    log.info(f"handling zfs event: {zevent}")
    zpool = env["ZEVENT_POOL"]

    # zpool event
    if zevent in ["scrub_finish", "scrub_start"]:
      zpool_status = get_zpool_status(zpool)

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
        cache.state = Since(ZFS_State.ONLINE, now)
      elif zevent == "statechange":
        if env["ZEVENT_VDEV_STATE_STR"] == "OFFLINE":
          log.info(f"zdev {cache.pool}:{cache.dev} went offline")
          cache.state = Since(ZFS_State.DISCONNECTED, now)
        else:
          log.warning(f"(potential bug) unknown statechange event: {env["ZEVENT_VDEV_STATE_STR"]}")
          cache.state = Since(ZFS_State.UNKNOWN, now)

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
        cache = find_or_create_cache(cache_dict, Disk, name=env["DM_NAME"])
    elif devtype == "partition":
      cache = find_or_create_cache(cache_dict, Partition, name=env["PARTNAME"])
    if cache != None:
      if action == "add":
        cache.state = Since(DM_Crypt_State.ONLINE, now)
      elif action == "remove":
        cache.state = Since(DM_Crypt_State.DISCONNECTED, now)

  save_cache(cache_dict, cache_file_path)









def daemon(args):

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

  log.info(f"Listening on {socket_path}")

  # Create a thread-safe list using a lock
  class ThreadSafeList:
    def __init__(self):
      self.list = []
      self.lock = threading.Lock()
      self.condition = threading.Condition(self.lock)

    def add_element(self, element):
      with self.condition:
        self.list.append(element)
        self.condition.notify()  # Notify any waiting threads

    def get_element(self):
      with self.condition:
        while not self.list:
          self.condition.wait()  # Wait for an element to be added
        return self.list.pop(0)

  def handle_client(connection, client_address, threadsafe_list):
    try:
      log.info(f"Connection from {client_address}")

      # Receive the data in small chunks and retransmit it
      while True:
        data = connection.recv(16)
        if data:
          threadsafe_list.add_element(data)
          connection.sendall(data)
        else:
          break
    finally:
      # Clean up the connection
      connection.close()

  def handle_event(threadsafe_list):
    while True:
      message = threadsafe_list.get_element()
      env = json.loads(message)[0]
      try:
        handle(env)
      except Exception as ex:
        log.error("failed to handle event: ", env)
        log.error("Exception: ", ex)

    

  # Create a thread-safe list
  threadsafe_list = ThreadSafeList()
  handle_event_thread = threading.Thread(target=handle_event, args=(threadsafe_list))
  handle_event_thread.start()
  try:
    while True:
      # Wait for a connection
      connection, client_address = server.accept()
      # Start a new thread for the connection
      client_thread = threading.Thread(target=handle_client, args=(connection, client_address, threadsafe_list))
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




