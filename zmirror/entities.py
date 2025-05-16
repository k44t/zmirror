import os
from datetime import datetime
import re


from .util import load_yaml_cache, load_yaml_config, save_yaml_cache, remove_yaml_cache, require_path
from .util import myexec as exec#pylint: disable=redefined-builtin
from .dataclasses import *

from .logging import log


from . import config
from . import util




# CONFIG_FILE_PATH = "/etc/zmirror/config.yml"
# CACHE_FILE_PATH = "/var/lib/zmirror/cache.yml"
# os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok = True)








def init_config(cache_path, config_path):
  config.cache_path = cache_path
  config.config_path = config_path
  os.makedirs(os.path.dirname(cache_path), exist_ok = True)
  config.cache_dict = load_yaml_cache(cache_path)
  if config.cache_dict is None:
    config.cache_dict = dict()
  config.config_dict = dict()
  config.lvm_physical_volumes = dict()
  config.zfs_blockdevs = dict()
  require_path(config.config_path, "config file does not exist")
  config.config_root = load_yaml_config(config.config_path)
  iterate_content_tree3(config.config_root, index_entities, None, None)
  iterate_content_tree3_depth_first(config.config_root, load_initial_state, None, None)
  iterate_content_tree3_depth_first(config.config_root, update_initial_state, None, None)

config.init = init_config


def load_initial_state(entity, _parent, _ignored):
  if hasattr(entity, "load_initial_state"):
    s = entity.load_initial_state()
    if s is not None:
      set_cache_state(cached(entity), s, True)

def update_initial_state(entity, _parent, _ignored):
  if hasattr(entity, "update_initial_state"):
    s = entity.update_initial_state()
    if s is not None:
      set_cache_state(cached(entity), s, True)


def index_entities(entity, parent, _ignored):
  if hasattr(entity, "parent"):
    entity.parent = parent
  if hasattr(entity, "id"):
    config.config_dict[entity_id_string(entity)] = entity
  # if isinstance(entity, LVMPhysicalVolume):
  #  if entity.lvm_volume_group in config.lvm_physical_volumes:
  #    config.lvm_physical_volumes[entity.lvm_volume_group].append(entity)
  #  else:
  #    config.lvm_physical_volumes[entity.lvm_volume_group] = [entity]
  if isinstance(entity, ZFSBackingBlockDevice):
    if entity.pool in config.zfs_blockdevs:
      config.zfs_blockdevs[entity.pool][entity.dev] = entity
    else:
      config.zfs_blockdevs[entity.pool] = {entity.dev: entity}
  return _ignored




def load_config_for_cache(cache):
  identifier = entity_id_string(cache)
  return load_config_for_id(identifier)

def load_config_for_id(identifier):
  local_config = None
  if identifier in config.config_dict:
    local_config = config.config_dict[identifier]
  else:
    log.error(f"id `{identifier}` not found in core.config_dict.")
  return local_config





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

def find_or_create_cache(typ, create_args=None, identifier_prefix=None, **kwargs):
  return util.find_or_create_cache(config.cache_dict, typ, create_args, identifier_prefix, **kwargs)

def find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path):
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/disk/by-partlabel/").removeprefix("/dev/")
  return find_or_create_cache(ZFSBackingBlockDevice, pool=zpool, dev=vdev_name)

def get_zpool_status(zpool_name):
  rcode, zpool_status, _, _ = exec(f"zpool status {zpool_name}")#pylint: disable=exec-used
  if rcode == 0:
    return zpool_status[0]
  else:
    return None



def remove_cache(cache_path):
  remove_yaml_cache(cache_path)

def save_cache():
  if config.cache_dict is None:
    raise ValueError("init() was not called")
  save_yaml_cache(config.cache_dict, config.cache_path)

def get_zfs_volume_mode(zfs_path):
  code, r, _, _ = exec(f"zfs get volmode {zfs_path}")
  if code == 0:
    return r
  else:
    return None



def is_zpool_backing_device_online(zpool, dev):
  status = config.get_zpool_status(zpool)
  if status is None:
    return False
  for match in POOL_DEVICES_REGEX.finditer(status):
    if match.group(1) == dev:
      return match.group(2) == "ONLINE"
  return False


POOL_DEVICES_REGEX = re.compile(r'^ {12}([-a-zA-Z0-9_]+) +([A-Z]+) +[0-9]+ +[0-9]+ +[0-9]+ *.*$', \
                         re.MULTILINE)



config.load_config_for_cache = load_config_for_cache
config.load_config_for_id = load_config_for_id
config.find_or_create_cache = find_or_create_cache
config.is_zpool_backing_device_online = is_zpool_backing_device_online
config.get_zpool_status = get_zpool_status