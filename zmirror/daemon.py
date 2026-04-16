
from collections import OrderedDict
import queue
from datetime import datetime
import re
import socket
import os
import threading
import json
import traceback
import stat
from enum import Enum
from threading import Timer
import signal
import sys
import time


from zmirror.user_commands import cancel_requests_for_timeout, enact_requests, handle_command

from . import defaults


from ._version import __version__

from . import commands
from .commands import CommandResultEvent
from .logging import log
from .entities import *
# from .actions import handle_entity_online, handle_entity_offline, handle_entity_present
from .dataclasses import * # , LVMLogicalVolume, VirtualDisk, 
from kpyutils.kiify import *

from . import config as globals


class EnvKey(Enum):
  # ZED (ZFS Event Daemon) environment for zevents.
  # See `zed` zedlets: these keys are exported by ZFS/zed.
  ZEVENT_SUBCLASS = "ZEVENT_SUBCLASS"  # Event type, e.g. pool_import, vdev_online.
  ZEVENT_POOL = "ZEVENT_POOL"  # Zpool name the zevent belongs to.
  ZEVENT_VDEV_PATH = "ZEVENT_VDEV_PATH"  # Vdev path, e.g. /dev/mapper/<name>.
  ZEVENT_VDEV_STATE_STR = "ZEVENT_VDEV_STATE_STR"  # New vdev state, e.g. OFFLINE.

  # udev environment keys from kernel uevents.
  # Available for block/dm devices handled by udev rules.
  DEVTYPE = "DEVTYPE"  # udev device type, usually "disk"/"partition".
  ACTION = "ACTION"  # udev action, e.g. add, remove, change.
  ID_PART_TABLE_UUID = "ID_PART_TABLE_UUID"  # Partition table UUID from udev ID_*.
  DM_NAME = "DM_NAME"  # device-mapper logical name, e.g. <pool>-b-main.
  DEVPATH = "DEVPATH"  # Kernel sysfs device path (/devices/...).
  DEVLINKS = "DEVLINKS"  # Space-separated /dev symlinks created by udev.
  PARTNAME = "PARTNAME"  # GPT partition name/label from udev.
  DM_ACTIVATION = "DM_ACTIVATION"  # dm activation status from udev dm rules.

  # zmirror's internal daemon command channel key.
  # This is injected by zmirror (not udev/zed) for socket commands.
  ZMIRROR_COMMAND = "ZMIRROR_COMMAND"


LOGGABLE_ENV_KEYS = tuple(sorted(key.value for key in EnvKey))


@dataclass
class UserEvent:
  event: dict
  con: socket.socket


def _counter_nonzero(value):
  try:
    return int(value) != 0
  except Exception:
    return value not in {"0", "-", ""}


POOL_SCRUB_ERRORS_REGEX = re.compile(r'^\s*scan:.*\bwith\s+(?P<errors>[0-9]+)\s+errors\b', re.MULTILINE)


def _parents_all_online(cache):
  entity = config.load_config_for_cache(cache)
  if entity is None:
    return False

  parent = getattr(entity, "parent", None)
  while isinstance(parent, Entity):
    if not is_online(parent):
      return False
    parent = getattr(parent, "parent", None)
  return True


def _collect_pool_status_snapshot(zpool, zpool_status=None):
  if zpool_status is None:
    try:
      zpool_status = config.get_zpool_status(zpool)
    except Exception as ex:
      log.debug(f"failed to get zpool status for pool {zpool}: {ex}")
      return None

  if zpool_status is None:
    return None

  devices = {}
  scrub_errors = None
  scrub_errors_match = POOL_SCRUB_ERRORS_REGEX.search(zpool_status)
  if scrub_errors_match is not None:
    scrub_errors = int(scrub_errors_match.group("errors"))

  for match in POOL_DEVICES_REGEX.finditer(zpool_status):
    dev = match.group("dev")
    if MIRROR_OR_RAIDZ_REGEX.match(dev):
      continue
    devices[dev] = {
      "state": match.group("state"),
      "read": match.group("read"),
      "write": match.group("write"),
      "cksum": match.group("cksum"),
      "operations": match.group("operations") or "",
      "errors": _counter_nonzero(match.group("read")) or _counter_nonzero(match.group("write")) or _counter_nonzero(match.group("cksum")),
    }

  return {
    "zpool": zpool,
    "scrub_errors": scrub_errors,
    "devices": devices,
  }


def _is_device_eligible(cache, status):
  return status["state"] == "ONLINE" and is_online_state(cache.state.what) and _parents_all_online(cache)


def _scrub_successful(snapshot, cache, status):
  scrub_errors = snapshot.get("scrub_errors")
  if scrub_errors is None or scrub_errors != 0:
    return False
  return _is_device_eligible(cache, status)


def update_vdev_error_state(snapshot):
  if snapshot is None:
    return

  try:
    devices = snapshot["devices"]
    zpool = snapshot["zpool"]
  except Exception as ex:
    log.debug(f"failed to update vdev error state from snapshot: {ex}")
    return

  for dev, status in devices.items():
    cache = find_or_create_cache(ZDev, pool=zpool, name=dev)
    eligible = _is_device_eligible(cache, status)
    if not eligible:
      cache.errors = False
      continue
    cache.errors = status["errors"]




def handle(env):
  log.debug("handling event")

  cache = None

  if config.log_events:
    relevant_env = OrderedDict((key, env[key]) for key in LOGGABLE_ENV_KEYS if key in env)
    if relevant_env:
      log.info(object_to_kdstring(relevant_env))
    else:
      log.info("event with no relevant keys registered")

  event_handled = False

  now = datetime.now()
  if EnvKey.ZEVENT_SUBCLASS.value in env:
    zevent = env[EnvKey.ZEVENT_SUBCLASS.value]
    log.debug(f"handling zfs event: {zevent}")
    zpool = env[EnvKey.ZEVENT_POOL.value]

    if zevent == "pool_export" or zevent == "pool_destroy":

      zpool_cache = find_or_create_cache(ZPool, name=zpool)
      handle_disconnected(zpool_cache)

      if zpool in globals.zfs_blockdevs:
        for dev in globals.zfs_blockdevs[zpool].values():
          dev_cache = find_or_create_cache(ZDev, pool=zpool, name=dev.name)
          handle_deactivated(dev_cache)
        # log.warning(f"{human_readable_id(zpool_cache)}: zpool destroyed. (You might need to update your zmirror configuration or recreate the pool.)")


      event_handled = True
    # zpool event
    elif zevent in ["scrub_finish", "scrub_start", "scrub_abort", "pool_import", "pool_create"]:
      log.debug(f"zpool {zpool}: {zevent}")
      zpool_status = config.get_zpool_status(zpool)
      pool_snapshot = _collect_pool_status_snapshot(zpool, zpool_status)
      update_vdev_error_state(pool_snapshot)




      found_online = False
      if zpool_status is None:
        log.error(f"zpool status failed for pool {zpool}")
      else:
        for match in POOL_DEVICES_REGEX.finditer(zpool_status):
          dev = match.group("dev")
          if MIRROR_OR_RAIDZ_REGEX.match(dev):
            continue

          cache = find_or_create_cache(ZDev, pool=zpool, name=dev)
          if match.group("state") == "ONLINE":

            found_online = True
            if zevent == "scrub_finish":
              if since_in(Operation.SCRUB, cache.operations):
                log.info(f"zdev {cache.pool}:{cache.name}: scrubbing finished")
                scrub_ok = False
                if pool_snapshot is not None and cache.name in pool_snapshot["devices"]:
                  scrub_ok = _scrub_successful(pool_snapshot, cache, pool_snapshot["devices"][cache.name])
                handle_scrub_finished(cache, successful_scrub=scrub_ok)
                event_handled = True
            elif zevent == "scrub_start":
              log.info(f"zdev {cache.pool}:{cache.name}: scrubbing started")
              handle_scrub_started(cache)
              event_handled = True
            elif zevent == "scrub_abort":
              log.info(f"zdev {cache.pool}:{cache.name}: scrubbing cancelled")
              handle_scrub_canceled(cache)
              event_handled = True
            elif zevent == "pool_import":
              log.debug(f"zdev {cache.pool}:{cache.name}: pool imported, device online")
              if "resilvering" in (match.group("operations") or ""):
                handle_resilver_started(cache)
                event_handled = True
              else:
                handle_onlined(cache)
                event_handled = True

      if zevent == "pool_import" or zevent == "pool_create":
        zpool_cache = find_or_create_cache(ZPool, name=zpool)
        
        handle_onlined(zpool_cache)
        event_handled = True

      if found_online is False:
        log.error("likely bug: zpool event but no devices online")

    # zpool-vdev event
    elif zevent in ["vdev_online", "statechange", "trim_start", "trim_finish", "trim_suspend", "trim_resume"]:
      # possible cases:
        # ZEVENT_POOL:: mypoolname
        # ZEVENT_VDEV_PATH:: /dev/mapper/mypoolname-b-main
        # ZEVENT_VDEV_PATH:: /dev/{vg_bak_gamma/lv_bak_gamma}
        # ZEVENT:: /dev/{sda3}
        # ZEVENT:: /dev/disk/by-partlabel/mypartlabel
      vdev_path = env[EnvKey.ZEVENT_VDEV_PATH.value]
      pool_snapshot = _collect_pool_status_snapshot(zpool)
      update_vdev_error_state(pool_snapshot)
      cache = find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path)
      if zevent == "vdev_online":
        # we have no event by witch we can reliably capture that a resilver started for a zdev
        # (resilver_started is a pool event). Hence we automatically assume that a zdev 
        # that is configured to be within a mirror (zpool.backing)
        # and that has been onlined in an active pool will resilver
        handle_zdev_onlined(cache)
        event_handled = True
      elif zevent == "statechange":
        new_state = env[EnvKey.ZEVENT_VDEV_STATE_STR.value]
        if new_state == "OFFLINE":
          handle_deactivated(cache)
          event_handled = True
        # else:
          # log.debug(f"unknown statechange event: { new_state }")
          # set_cache_state(cache, EntityState.UNKNOWN)
      elif zevent == "trim_start" or zevent == "trim_resume":
        handle_trim_started(cache)
        event_handled = True
      elif zevent == "trim_finish":
        handle_trim_finished(cache)
        event_handled = True
      elif zevent == "trim_suspend":
        handle_trim_canceled(cache)
        event_handled = True

    # zool-vdev event
    elif zevent in ["resilver_start", "resilver_finish"]:

      # sometimes resilver_finish is not being recognized
      # maybe the zevent is too fast, so we wait just a little
      time.sleep(0.25)

      zpool_status = config.get_zpool_status(zpool)
      pool_snapshot = _collect_pool_status_snapshot(zpool, zpool_status)
      update_vdev_error_state(pool_snapshot)
      
      for match in POOL_DEVICES_REGEX.finditer(zpool_status):
        if match.group("state") == "ONLINE":
          dev = match.group("dev")
          cache = find_or_create_cache(ZDev, pool=zpool, name=dev)


          if zevent == "resilver_start":
            if "resilvering" in (match.group("operations") or ""):
              # this method will only have an effect if the operation is not currently resilvering
              # hence this should never have an effect, because we assume that mirrored devices will
              # start resilvering the moment they come online.
              handle_resilver_started(cache)
              event_handled = True
          else:
            log.verbose(f"{human_readable_id(cache)}: handling resilver_finish")
            if "resilvering" not in (match.group("operations") or ""):
              if since_in(Operation.RESILVER, cache.operations):
                handle_resilver_finished(cache)
                event_handled = True

          

  elif EnvKey.DEVTYPE.value in env:
    action = env[EnvKey.ACTION.value]
    devtype = env[EnvKey.DEVTYPE.value]
    log.debug(f"handling udev block event: {action}")


    if action == "add" or action == "remove":
      if devtype == "disk":
        if EnvKey.ID_PART_TABLE_UUID.value in env:
          cache = find_or_create_cache(Disk, uuid=env[EnvKey.ID_PART_TABLE_UUID.value])
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
        elif EnvKey.DM_NAME.value in env:
          cache = find_or_create_cache(DMCrypt, name=env[EnvKey.DM_NAME.value])
          if action == "add":
            handle_onlined(cache)
          else:
            handle_deactivated(cache)
          event_handled = True

        # virtual device
        elif EnvKey.DEVPATH.value in env and env[EnvKey.DEVPATH.value].startswith("/devices/virtual/block/"):
          if env[EnvKey.DEVPATH.value].startswith("/devices/virtual/block/zd"):
            devlinks = env[EnvKey.DEVLINKS.value].split(" ")
            for devlink in devlinks:
              match = re.match(r'/dev/zvol/(?P<pool>[^/]+)/(?P<volume>.+)$', devlink)
              if match and not re.match(r'-part[0-9]+$', match.group("volume")):
                # zfs-volume state transitions are virtual and follow parent pool state.
                # We keep zvol udev events as handled but do not map them to state changes.
                event_handled = True
                break
          # elif "ID_FS_UUID" in env:
          #  cache = find_or_create_cache(VirtualDisk, fs_uuid=env["ID_FS_UUID"])
          #  udev_event_action(cache, action, now)
          #  log.info(f"{cache.__class__.__name__} {cache.fs_uuid}: {to_kd(cache.state)}")
          #  event_handled = True
          else:
            log.debug("need a filesystem uuid or a zvol devlink (if applicable) to identify virtual blockdevices")
        else:
          log.debug("nothing to do for disk event")

      elif devtype == "partition":
        # sometimes, while modifying partitions, there appears an event concerning the partition
        # that not yet contains a PARTNAME
        if EnvKey.PARTNAME.value in env:
          cache = find_or_create_cache(Partition, name=env[EnvKey.PARTNAME.value])
          udev_event_action(cache, action, now)
          event_handled = True
    
    # this UDEV event means that the DMCrypt was `open`ed
    elif action == "change" and EnvKey.DM_ACTIVATION.value in env and env[EnvKey.DM_ACTIVATION.value] == "1":
      devlinks = env[EnvKey.DEVLINKS.value].split(" ")
      for devlink in devlinks:
        match = re.match(r'/dev/mapper/([^/]+)$', devlink)
        if match:
          dm_name = match.group(1)

          cache = find_or_create_cache(DMCrypt, name=dm_name)
          handle_onlined(cache)
          event_handled = True

          break
  if event_handled:
    log.debug("event handled by zmirror")
    return True
  else:
    log.debug("event not handled by zmirror")
    return False






def udev_event_action(entity, action, now):
  if action == "add":
    handle_onlined(entity)
  elif action == "remove":
    handle_disconnected(entity)



def handle_client(con: socket.socket, client_address, event_queue: queue.Queue):
  try:
    log.debug(f"client connected")


    # Read until ':' to get the length
    length_str = ""
    while True:
        char = con.recv(1).decode('utf-8')
        if char == ':':
            break
        length_str += char

    # Convert length to integer
    try:
      total_length = int(length_str)
    except:
      log.error("client did not send length of message")
      con.close()
      return


    # Read the JSON data of the specified length
    data = b""
    while len(data) < total_length:
        more_data = con.recv(total_length - len(data))
        if not more_data:
            raise ConnectionError("Connection closed before receiving all data")
        data += more_data

    message = data.decode('utf-8')
    event = json.loads(message)
    if EnvKey.ZMIRROR_COMMAND.value in event:
      event_queue.put(UserEvent(event[EnvKey.ZMIRROR_COMMAND.value], con))
    else:
      event_queue.put(event)
    log.debug("registered event")
    # print("registered event")
  except Exception:
    log.error("communication error", exc_info=config.log_level <= logging.DEBUG)


def handle_events(event_queue, shutdown_fn):
  while True:
    handled = False
    try:
      event = event_queue.get()
      if event is None:
        # this is the SHUTDOWN, shutting down
        log.info("handling shutdown event")
        try:
          save_cache_now()
        except BaseException as _ex:
          log.error("failed to save cache")
        shutdown_fn()
        break
      elif isinstance(event, UserEvent):
        
        handled = handle_command(event.event, event.con)

      elif isinstance(event, CommandResultEvent):
        event.cmd.handle(event.returncode, event.results, event.errors)
        handled = True
        

      elif isinstance(event, TimerEvent):
        log.debug(f"timer event: ({config.timeout})")
        handled = event.action()
      else:
        handled = handle(event)
      
      if handled:
        save_cache()
        enact_requests()
        commands.execute_commands()
    except Exception as ex:
      try:
        log.error(f"failed to handle event: {json.dumps(event, indent=2)}")
        log.error(f"Exception : {traceback.format_exc()} --- {str(ex)}")
      except: 
        pass
    # print("event loop has run")
    
  
def is_socket_active(socket_path):
  if not os.path.exists(socket_path):
      return False
  client_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
  try:
    client_sock.connect(socket_path)
    return True
  except socket.error:
    return False
  finally:
    try:
      client_sock.close()
    except:
      pass

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
  
  # Check if systemd is available
  try:
    from systemd.journal import JournalHandler # type: ignore # pylint: disable=import-outside-toplevel

    journal_handler = JournalHandler()
    formatter = logging.Formatter('%(levelname)7s: %(message)s')
    journal_handler.setFormatter(formatter)
    logging.getLogger().addHandler(journal_handler)
  except ImportError:
    log.warning("systemd log not available")

  log.info(f"zmirror daemon version {__version__} starting")

  config.is_daemon = True


  socket_path = args.socket_path
  # Define the path for the Unix socket

  # Create a UDS (Unix Domain Socket)
  server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

  socket_dir = os.path.dirname(socket_path)

  # Bind the socket to the path
  try:
    os.makedirs(socket_dir, exist_ok=True)
  except Exception as ex:
    log.error(f"could not create parent directory for socket path: {socket_path}: {ex}")
    return
  try:
    log.debug(f"setting permissions 700 on {socket_dir}")
    os.chmod(socket_dir, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
  except Exception as ex:
    log.error(f"could not set permissions on {socket_dir}: {ex}")
    return
  if is_socket_active(socket_path):
    log.error(f"socket already in use: {socket_path}")
    return
  else:
    if os.path.exists(socket_path):
      log.warning(f"file {socket_path} exists but no zmirror daemon listening, deleting.")
      os.unlink(socket_path)
  try:
    server.bind(socket_path)
  except Exception as ex:
    log.error(f"could not bind unix socket: {socket_path}: {ex}")
    return
  try:
    log.debug(f"setting permissions 400 on {socket_path}")
    os.chmod(socket_path, stat.S_IRUSR | stat.S_IWUSR)
  except Exception as ex:
    log.debug(f"failed to set permissions on {socket_path}")


  # Listen for incoming connections
  server.listen()

  log.info(f"listening on {socket_path}")



  event_queue = queue.Queue()
  config.event_queue = event_queue
  commands.start_workers(event_queue, num_workers=1)



  def shutdown(*args):
    if config.running:
      config.running = False
      log.info("shutting down...")
      try:
        server.close()
      except Exception:
        pass
      try:
        os.unlink(socket_path)
      except Exception:
        pass
      try:
        config.cancel_timers()
      except Exception:
        pass
      try:
        commands.stop_workers()
      except Exception:
        pass

      event_queue.put(None)
      try:
        # if it comes from the current thread this will raise an exception
        handle_event_thread.join()
      except:
        pass
      log.info("zmirror daemon finished")
      
      # this is necessary if some timeouts are still pending (timer threads may keep running after sys.exit has been called)
      # os.kill(os.getpid(), signal.SIGKILL) #pylint: disable=unreachable
      sys.exit(0)

      time.sleep(1)

      # this is necessary if some timeouts are still pending (timer threads may keep running after sys.exit has been called)
      os.kill(os.getpid(), signal.SIGKILL) #pylint: disable=unreachable



  # Create a thread-safe list
  handle_event_thread = threading.Thread(target=handle_events,args=(event_queue, shutdown))
  handle_event_thread.start()


  # we load the config after we have started the server, so that we cannot miss any events that might change the config while it is being loaded
  init_config(cache_path=args.cache_path, config_path=args.config_path)


  signal.signal(signal.SIGTERM, shutdown)
  signal.signal(signal.SIGINT, shutdown)

  try:
    while config.running:
      # Wait for a connection
      connection, client_address = server.accept()
      # Start a new thread for the connection
      client_thread = threading.Thread(target=handle_client, args=(connection, client_address, event_queue))
      client_thread.start()
  except Exception as exception:
    log.error(str(exception))
  finally:
    if config.running:
      shutdown()
