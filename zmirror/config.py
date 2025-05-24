import os
from datetime import datetime
from threading import Timer
import logging

lvm_physical_volumes = dict()
zfs_blockdevs = dict()


cache_dict: dict = None
config_root = None
config_dict: dict = None
cache_path = None
config_path = None
disable_commands = False
last_request_at = datetime.now()
log_level = logging.INFO

is_daemon = False


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

def get_zfs_volume_mode(zfs_path):
  raise NotImplementedError()

def is_zpool_backing_device_online(pool, dev):
  raise NotImplementedError()

def get_zpool_status(pool):
  raise NotImplementedError()

def load_config_for_id(arg):
  raise NotImplementedError()

def find_config(typ, **args):
  raise NotImplementedError()