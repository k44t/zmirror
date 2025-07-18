import os
from datetime import datetime
from threading import Timer
import logging
from .logging import log

lvm_physical_volumes = dict()
zfs_blockdevs = dict()


cache_dict: dict = None
config_root = None
config_dict: dict = None
cache_path = None
config_path = None
commands_enabled = False
last_request_at = datetime.now()
log_level = logging.INFO
event_queue = None
timeout = None


is_daemon = False


class TimerEvent:
  def __init__(self, action):
    self.action = action


def dev_exists(dev_path):
  if dev_path.startswith("/dev/"):
    return os.path.exists(dev_path)
  return os.path.exists("/dev/" + dev_path)


def find_provisioning_mode(dev_link):
  dev_path = os.path.realpath(dev_link)
  dev_name = dev_path[5:]
  path = f"/sys/block/{dev_name}/device"
  if os.path.exists(path):
    for root, dirs, files in os.walk(path):
      if 'provisioning_mode' in files:
        return os.path.join(root, 'provisioning_mode')
  return None

def set_log_level(level):  
  global log_level
  if not level in log_level_for_name:
    raise ValueError(f"unknown loglevel: {level}")
  log_level = log_level_for_name[level]
  logging.getLogger().setLevel(log_level)

def get_zfs_volume_mode(zfs_path):
  raise NotImplementedError()

def get_zpool_backing_device_state(pool, dev):
  raise NotImplementedError()

def get_zpool_status(pool):
  raise NotImplementedError()

def load_config_for_id(arg):
  raise NotImplementedError()


def find_config(typ, **args):
  raise NotImplementedError()


log_level_for_name = {
  "trace": 5,
  "debug": logging.DEBUG,
  "info": logging.INFO,
  "warning": logging.WARNING,
  "error": logging.ERROR,
  "critical": logging.CRITICAL,
}




def iterate_content_tree3(o, fn, parent, strt):
  result = fn(o, parent, strt)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        result = iterate_content_tree3(e, fn, o, result)
  return result

def iterate_content_tree3_depth_first(o, fn, parent, strt):
  result = strt
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        result = iterate_content_tree3_depth_first(e, fn, o, result)
  result = fn(o, parent, result)
  return result


def iterate_content_tree2(o, fn, strt):
  result = fn(o, strt)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        result = iterate_content_tree2(e, fn, result)
  return result

def iterate_content_tree(o, fn):
  result = []
  fresult = fn(o)
  if fresult is not None:
    result.append(o)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        rlst = iterate_content_tree(e, fn)
        result = result + rlst
  return result
