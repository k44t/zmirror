import os
from datetime import datetime
import re
import logging

from .util import load_yaml_cache, load_yaml_config, save_yaml_cache, remove_yaml_cache, require_path
from .util import myexec as exec#pylint: disable=redefined-builtin
from .dataclasses import *

from .logging import log
from kpyutils.kiify import *


from . import config
from .config import iterate_content_tree, iterate_content_tree2, iterate_content_tree3, iterate_content_tree3_depth_first, log_level_for_name
from . import util




# CONFIG_FILE_PATH = "/config.yml"
# CACHE_FILE_PATH = "/var/lib/zmirror/cache.yml"
# os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok = True)







def init_config(cache_path, config_path):
  config.cache_path = cache_path
  config.config_path = config_path


  require_path(config.config_path, "config file does not exist")
  config.config_root = load_yaml_config(config.config_path)

  config.set_log_level(config.config_root.log_level)


  config.timeout = int(config.config_root.timeout)

  config.log_events = config.config_root.log_events

  os.makedirs(os.path.dirname(cache_path), exist_ok = True)
  log.info(f"loading cache from: f{cache_path}")
  config.cache_dict = load_yaml_cache(cache_path)
  if config.cache_dict is None:
    config.cache_dict = dict()
  config.config_dict = dict()
  config.lvm_physical_volumes = dict()
  config.zfs_blockdevs = dict()
    

  config.find_config = find_config

  iterate_content_tree3(config.config_root, index_entities, None, None)
  iterate_content_tree3_depth_first(config.config_root, load_initial_state, None, None)
  iterate_content_tree3_depth_first(config.config_root, update_initial_state, None, None)

  iterate_content_tree3(config.config_root, finalize_init, None, None)

  config.commands_enabled = config.config_root.enable_commands
  log.info(f"command execution enabled: {to_yes(config.commands_enabled)}")

  commands.execute_commands()

def finalize_init(entity, _parent, _ignored):
  if isinstance(entity, Entity):
    cache = cached(entity)
    if cache.state.what in {EntityState.INACTIVE, EntityState.ONLINE}:
      statstr = f"{human_readable_id(entity)}: {cache.state.what.name}"
      if hasattr(cache, "operations"):
        for i, op in enumerate(cache.operations):
          if i == 0:
            statstr += " (active operations: "
          else:
            stastr += ", "
          statstr += op.what.name.lower()
          if i == 0:
            statstr += ")"
      log.info(statstr)
    if hasattr(entity, "finalize_init"):
      entity.finalize_init()

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
  if isinstance(entity, ZDev):
    if entity.pool in config.zfs_blockdevs:
      config.zfs_blockdevs[entity.pool][entity.dev_name()] = entity
    else:
      config.zfs_blockdevs[entity.pool] = {entity.dev_name(): entity}
  return _ignored




def load_config_for_cache(cache):
  identifier = entity_id_string(cache)
  return load_config_for_id(identifier)

def load_config_for_id(identifier):
  local_config = None
  if identifier in config.config_dict:
    local_config = config.config_dict[identifier]
  return local_config



def find_config(typ, **identifier):
  return load_config_for_id(make_id_string(make_id(typ, **identifier)))



def find_or_create_cache(typ, create_args=None, identifier_prefix=None, **kwargs):
  return util.find_or_create_cache(config.cache_dict, typ, create_args, identifier_prefix, **kwargs)

def find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path):
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/disk/by-partlabel/").removeprefix("/dev/")
  return find_or_create_cache(ZDev, pool=zpool, name=vdev_name)

def get_zpool_status(zpool_name):
  return simple_string_command(f"zpool status {zpool_name}", f"failed to get status of zpool {zpool_name}", log.debug)


def simple_string_command(command, error, logfn=log.error):
  rcode, zpool_status, _, _ = exec(command)#pylint: disable=exec-used
  if rcode == 0:
    return "\n".join(zpool_status)
  else:
    logfn(error)
    return None
  
def get_zfs_volume_mode(zfs_path):
  return simple_string_command(f"zfs get volmode {zfs_path}", f"failed to get volmode of zfs volume {zfs_path}", log.debug)



def remove_cache(cache_path):
  remove_yaml_cache(cache_path)

def save_cache():
  if config.cache_dict is None:
    raise ValueError("init() was not called")
  save_yaml_cache(config.cache_dict, config.cache_path)




def get_zpool_backing_device_state(zpool, dev):
  status = config.get_zpool_status(zpool)
  if status is None:
    return None
  opers = set()
  scrubbing = "scrub in progress" in status
  state = EntityState.DISCONNECTED
  for match in POOL_DEVICES_REGEX.finditer(status):
    if match.group("dev") == dev:
      state = match.group("state")
      if state == "ONLINE":
        state = EntityState.ONLINE
        if scrubbing:
          opers.add(Operation.SCRUB)
      else:
        state = EntityState.INACTIVE
      opernames = match.group("operations")
      if opernames is not None:
        if "resilver" in opernames:
          opers.add(Operation.RESILVER)
        if "trim" in opers:
          opers.add(Operation.TRIM)
      return (state, opers)
  return None

POOL_SCRUBBING_REGEX = re.compile(r'scrub in progress', re.MULTILINE)

POOL_DEVICES_REGEX = re.compile(r'^\t  (?:  )?(?P<dev>[^\s]+)\s+(?P<state>[^\s]+)\s+(?P<read>[^\s]+)\s+(?P<write>[^\s]+)\s+(?P<cksum>[^\s]+)\s*(?:\s* \((?P<operations>.+)\))?\s*$', 
  # multiline must be set for this expression to work
  # my guess is, that this makes `^` and `$` work as desired.
  re.MULTILINE)

MIRROR_OR_RAIDZ_REGEX = re.compile(r"^(raidz[0-9]+|mirror-[0-9])+$")


config.load_config_for_cache = load_config_for_cache
config.load_config_for_id = load_config_for_id
config.find_or_create_cache = find_or_create_cache
config.get_zpool_backing_device_state = get_zpool_backing_device_state
config.get_zpool_status = get_zpool_status
config.get_zfs_volume_mode = get_zfs_volume_mode
