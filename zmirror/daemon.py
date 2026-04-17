
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

RESILVER_START_DELAY = 5
_pending_resilver_start_checks = {}


@dataclass
class UserEvent:
  event: dict
  con: socket.socket


@dataclass
class DelayedResilverStartCheckEvent:
  zpool: str


@dataclass
class RegularStatusCheckEvent:
  zpool: str = None


def _counter_nonzero(value):
  try:
    return int(value) != 0
  except Exception:
    return value not in {"0", "-", ""}


def _leaf_vdevs(vdevs):
  if not isinstance(vdevs, dict):
    return
  for vdev in vdevs.values():
    if not isinstance(vdev, dict):
      continue
    nested = vdev.get("vdevs")
    if isinstance(nested, dict) and nested:
      yield from _leaf_vdevs(nested)
    else:
      yield vdev


def _pool_status_data(zpool, zpool_status):
  if not isinstance(zpool_status, dict):
    return None
  pools = zpool_status.get("pools", {})
  if not isinstance(pools, dict):
    return None
  pool_data = pools.get(zpool)
  if not isinstance(pool_data, dict):
    return None
  return pool_data


def _pool_resilvering(snapshot):
  pool_data = snapshot.get("pool") if isinstance(snapshot, dict) else None
  if not isinstance(pool_data, dict):
    return False
  scan_stats = pool_data.get("scan_stats", {})
  if not isinstance(scan_stats, dict):
    return False
  fn = str(scan_stats.get("function", "")).upper()
  st = str(scan_stats.get("state", "")).upper()
  return fn == "RESILVER" and st not in {"FINISHED", "NONE", "-", ""}


def _online_snapshot_devices(snapshot):
  devices = snapshot.get("devices", {}) if isinstance(snapshot, dict) else {}
  if not isinstance(devices, dict):
    return set()
  return {dev for dev, status in devices.items() if status.get("state") == "ONLINE"}


def _reliable_resilver_targets(snapshot):
  devices = snapshot.get("devices", {}) if isinstance(snapshot, dict) else {}
  if not isinstance(devices, dict):
    return set()

  online = _online_snapshot_devices(snapshot)
  with_explicit_resilver = {dev for dev in online if devices[dev].get("resilvering")}
  if with_explicit_resilver:
    return with_explicit_resilver

  if not _pool_resilvering(snapshot):
    return set()

  return {dev for dev in online if devices[dev].get("scan_processed") is not None}


def _pool_has_updating_device(zpool):
  for dev in config.zfs_blockdevs.get(zpool, {}).keys():
    cache = find_or_create_cache(ZDev, pool=zpool, name=dev)
    if is_online_state(cache.state.what) and since_in(Operation.RESILVER, cache.operations):
      return True
  return False


def _apply_resilver_start_from_snapshot(snapshot, allow_fallback=False):
  if snapshot is None or not _pool_resilvering(snapshot):
    return False

  targets = _reliable_resilver_targets(snapshot)
  if allow_fallback and not targets and not _pool_has_updating_device(snapshot["zpool"]):
    targets = _online_snapshot_devices(snapshot)

  handled = False
  for dev in targets:
    cache = find_or_create_cache(ZDev, pool=snapshot["zpool"], name=dev)
    if not is_online_state(cache.state.what):
      continue
    handle_resilver_started(cache)
    handled = True
  return handled


def _apply_resilver_finish_from_snapshot(snapshot):
  if snapshot is None:
    return False

  handled = False
  active_targets = _reliable_resilver_targets(snapshot) if _pool_resilvering(snapshot) else set()
  for dev in config.zfs_blockdevs.get(snapshot["zpool"], {}).keys():
    cache = find_or_create_cache(ZDev, pool=snapshot["zpool"], name=dev)
    if not is_online_state(cache.state.what):
      continue
    if dev in active_targets:
      continue
    if since_in(Operation.RESILVER, cache.operations):
      log.verbose(f"{human_readable_id(cache)}: handling resilver_finish")
      handle_resilver_finished(cache)
      handled = True
  return handled


def _queue_synthetic_event(event):
  if config.event_queue is None:
    return False
  config.event_queue.put(event)
  return False


def _clear_pending_resilver_start_check(zpool):
  timer = _pending_resilver_start_checks.pop(zpool, None)
  if timer is None:
    return
  timer.cancel()
  try:
    config.timers.remove(timer)
  except Exception:
    pass


def _handle_delayed_resilver_start(event):
  zpool = event.zpool
  _pending_resilver_start_checks.pop(zpool, None)

  try:
    zpool_status = config.get_zpool_status(zpool)
  except Exception as ex:
    log.debug(f"failed to get zpool status for delayed resilver check on pool {zpool}: {ex}")
    zpool_status = None
  pool_snapshot = _collect_pool_status_snapshot(zpool, zpool_status)
  handled = _apply_resilver_start_from_snapshot(pool_snapshot, allow_fallback=True)
  update_vdev_error_state(pool_snapshot)
  return handled


def _handle_regular_status_check(event):
  checked = False
  if event.zpool is None:
    try:
      zpool_status = get_all_zpool_status()
    except Exception as ex:
      log.debug(f"failed to get zpool status for regular status check: {ex}")
      zpool_status = None
    pools = list(config.zfs_blockdevs.keys())
  else:
    try:
      zpool_status = config.get_zpool_status(event.zpool)
    except Exception as ex:
      log.debug(f"failed to get zpool status for regular status check on pool {event.zpool}: {ex}")
      zpool_status = None
    pools = [event.zpool]

  handled = False
  for zpool in pools:
    pool_snapshot = _collect_pool_status_snapshot(zpool, zpool_status)
    if pool_snapshot is not None:
      checked = True
    handled = _apply_resilver_start_from_snapshot(pool_snapshot) or handled
    update_vdev_error_state(pool_snapshot)
  return handled or checked


def _schedule_delayed_resilver_start(zpool):
  if zpool in _pending_resilver_start_checks:
    return False
  timer = config.start_event_queue_timer(RESILVER_START_DELAY, lambda: _queue_synthetic_event(DelayedResilverStartCheckEvent(zpool)))
  _pending_resilver_start_checks[zpool] = timer
  return True


def _resilver_activation_targets(snapshot):
  reliable_targets = _reliable_resilver_targets(snapshot)
  if reliable_targets:
    return reliable_targets
  if snapshot is None or not _pool_resilvering(snapshot):
    return set()
  return _online_snapshot_devices(snapshot)


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

  pool_data = _pool_status_data(zpool, zpool_status)
  if pool_data is None:
    return None

  devices = {}
  scrub_errors = None
  scan_stats = pool_data.get("scan_stats", {})
  if isinstance(scan_stats, dict):
    scan_errors = scan_stats.get("errors")
    if scan_errors is not None:
      try:
        scrub_errors = int(scan_errors)
      except Exception:
        scrub_errors = None

  pool_vdevs = pool_data.get("vdevs", {})
  root_vdev = pool_vdevs.get(zpool, {}) if isinstance(pool_vdevs, dict) else {}
  root_children = root_vdev.get("vdevs", {}) if isinstance(root_vdev, dict) else {}

  for vdev in _leaf_vdevs(root_children):
    dev = vdev.get("name")
    if not isinstance(dev, str):
      continue
    if MIRROR_OR_RAIDZ_REGEX.match(dev):
      continue
    read_errors = vdev.get("read_errors", "0")
    write_errors = vdev.get("write_errors", "0")
    cksum_errors = vdev.get("checksum_errors", "0")
    operations = vdev.get("operations", [])
    if isinstance(operations, (list, tuple, set)):
      operations_text = ",".join(map(str, operations)).lower()
    else:
      operations_text = str(operations).lower()

    devices[dev] = {
      "state": str(vdev.get("state", "")),
      "read": read_errors,
      "write": write_errors,
      "cksum": cksum_errors,
      "scan_processed": vdev.get("scan_processed"),
      "resilvering": "resilver" in operations_text,
      "errors": str(vdev.get("state", "")).upper() != "ONLINE" or _counter_nonzero(read_errors) or _counter_nonzero(write_errors) or _counter_nonzero(cksum_errors),
    }

  return {
    "zpool": zpool,
    "scrub_errors": scrub_errors,
    "pool": pool_data,
    "devices": devices,
  }


def _is_device_eligible(cache, status):
  return status["state"] == "ONLINE" and is_online_state(cache.state.what) and _parents_all_online(cache)


def _scrub_successful(snapshot, cache, status):
  scrub_errors = snapshot.get("scrub_errors")
  if scrub_errors is None or scrub_errors != 0:
    return False
  return _is_device_eligible(cache, status)


def _pool_status_has_errors(snapshot):
  if snapshot is None:
    return False

  scrub_errors = snapshot.get("scrub_errors")
  if scrub_errors not in {None, 0}:
    return True

  pool_data = snapshot.get("pool") if isinstance(snapshot, dict) else None
  if not isinstance(pool_data, dict):
    return False

  error_count = pool_data.get("error_count")
  try:
    if error_count is not None and int(error_count) != 0:
      return True
  except Exception:
    if error_count not in {None, "0", "", "-"}:
      return True

  devices = snapshot.get("devices", {}) if isinstance(snapshot, dict) else {}
  saw_offline_device = False
  if isinstance(devices, dict):
    for status in devices.values():
      device_state = str(status.get("state", "")).upper()
      if device_state not in {"", "ONLINE", "OFFLINE"}:
        return True
      if device_state == "OFFLINE":
        saw_offline_device = True
      if device_state == "ONLINE" and bool(status.get("errors")):
        return True

  pool_state = str(pool_data.get("state", "")).upper()
  if pool_state == "DEGRADED":
    pool_status = str(pool_data.get("status", "")).lower()
    admin_offline = "taken offline by the administrator" in pool_status
    if admin_offline and saw_offline_device:
      return False
    return True

  if pool_state and pool_state not in {"ONLINE", "OFFLINE"}:
    return True

  return False


def update_zpool_error_state(snapshot):
  if snapshot is None:
    return

  zpool = snapshot.get("zpool")
  if zpool is None:
    return

  cache = find_or_create_cache(ZPool, name=zpool)
  if not is_online_state(cache.state.what):
    return

  cache.errors = _pool_status_has_errors(snapshot)


def update_vdev_error_state(snapshot):
  if snapshot is None:
    return

  try:
    devices = snapshot["devices"]
    zpool = snapshot["zpool"]
  except Exception as ex:
    log.debug(f"failed to update vdev error state from snapshot: {ex}")
    return

  configured_devs = config.zfs_blockdevs.get(zpool, {})
  for dev in configured_devs.keys():
    cache = find_or_create_cache(ZDev, pool=zpool, name=dev)
    if not is_online_state(cache.state.what):
      continue

    status = devices.get(dev)
    if status is None:
      cache.errors = True
      continue

    cache.errors = bool(status["errors"])

  update_zpool_error_state(snapshot)




def handle(env):
  log.debug("handling event")

  cache = None

  if config.log_full_events:
    full_env = OrderedDict((key, env[key]) for key in sorted(env.keys()))
    if full_env:
      log.info(object_to_kdstring(full_env))
    else:
      log.info("event with empty env")
  elif config.log_events:
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
      _clear_pending_resilver_start_check(zpool)

      zpool_cache = find_or_create_cache(ZPool, name=zpool)
      handle_disconnected(zpool_cache)

      if zpool in globals.zfs_blockdevs:
        for dev in globals.zfs_blockdevs[zpool].values():
          dev_cache = find_or_create_cache(ZDev, pool=zpool, name=dev.name)
          handle_deactivated(dev_cache)
        # log.warning(f"{human_readable_id(zpool_cache)}: zpool destroyed. (You might need to update your zmirror configuration or recreate the pool.)")


      event_handled = True
    # zpool event
    elif zevent in ["scrub_finish", "scrub_start", "scrub_abort", "pool_import", "pool_create", "config_sync"]:
      log.debug(f"zpool {zpool}: {zevent}")
      zpool_status = config.get_zpool_status(zpool)
      pool_snapshot = _collect_pool_status_snapshot(zpool, zpool_status)
      found_online = False
      if pool_snapshot is None:
        log.error(f"zpool status failed for pool {zpool}")
      else:
        for dev, status in pool_snapshot["devices"].items():
          cache = find_or_create_cache(ZDev, pool=zpool, name=dev)
          if status["state"] == "ONLINE":

            found_online = True
            if zevent == "scrub_finish":
              if since_in(Operation.SCRUB, cache.operations):
                log.info(f"zdev {cache.pool}:{cache.name}: scrubbing finished")
                scrub_ok = False
                scrub_ok = _scrub_successful(pool_snapshot, cache, status)
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
              handle_onlined(cache)
              event_handled = True

      if zevent == "pool_import" or zevent == "pool_create":
        zpool_cache = find_or_create_cache(ZPool, name=zpool)
        
        handle_onlined(zpool_cache)
        event_handled = True

      if zevent == "config_sync":
        event_handled = _handle_regular_status_check(RegularStatusCheckEvent(zpool)) or event_handled

      if found_online is False:
        log.error("likely bug: zpool event but no devices online")

      update_vdev_error_state(pool_snapshot)

    # zpool-vdev event
    elif zevent == "vdev_clear":
      vdev_path = env.get(EnvKey.ZEVENT_VDEV_PATH.value)
      if vdev_path:
        cache = find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path)
        log.debug(f"vdev_clear: recorded clear event for zdev {cache.pool}:{cache.name}")
        event_handled = True
      else:
        log.debug("vdev_clear event missing ZEVENT_VDEV_PATH")

    elif zevent in ["vdev_online", "statechange", "trim_start", "trim_finish", "trim_suspend", "trim_resume"]:
      # possible cases:
        # ZEVENT_POOL:: mypoolname
        # ZEVENT_VDEV_PATH:: /dev/mapper/mypoolname-b-main
        # ZEVENT_VDEV_PATH:: /dev/{vg_bak_gamma/lv_bak_gamma}
        # ZEVENT:: /dev/{sda3}
        # ZEVENT:: /dev/disk/by-partlabel/mypartlabel
      vdev_path = env[EnvKey.ZEVENT_VDEV_PATH.value]
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
      if zevent == "resilver_start":
        event_handled = _schedule_delayed_resilver_start(zpool)
      else:
        _clear_pending_resilver_start_check(zpool)

        # sometimes resilver_finish is not being recognized
        # maybe the zevent is too fast, so we wait just a little
        time.sleep(0.25)

        zpool_status = config.get_zpool_status(zpool)
        pool_snapshot = _collect_pool_status_snapshot(zpool, zpool_status)
        event_handled = _apply_resilver_finish_from_snapshot(pool_snapshot) or event_handled

          

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
                # zvol state transitions are virtual and follow parent pool state.
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
      elif isinstance(event, DelayedResilverStartCheckEvent):
        handled = _handle_delayed_resilver_start(event)
      elif isinstance(event, RegularStatusCheckEvent):
        handled = _handle_regular_status_check(event)
      elif callable(event):
        handled = event()
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
  server.settimeout(1.0)

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
        for attr in ["update_scheduler", "maintenance_scheduler", "regular_status_scheduler"]:
          scheduler = getattr(config, attr, None)
          if scheduler is not None:
            scheduler.cancel()
            setattr(config, attr, None)
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
      try:
        # Wait for a connection
        connection, client_address = server.accept()
      except socket.timeout:
        continue
      except OSError as exception:
        if config.running:
          log.error(str(exception))
        break

      # Start a new thread for the connection
      client_thread = threading.Thread(target=handle_client, args=(connection, client_address, event_queue))
      client_thread.start()
  finally:
    if config.running:
      shutdown()
