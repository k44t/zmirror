import os
from pyutils import load_yaml_cache, load_yaml_config, save_yaml_cache, remove_yaml_cache, find_or_create_cache
from pyutils import myexec as exec#pylint: disable=redefined-builtin
from zmirror_dataclasses import ZFSBlockdevCache
from zmirror_logging import log
import zmirror_commands as commands


log.info("starting zmirror")

CONFIG_FILE_PATH = "/etc/zmirror/config.yml"
CACHE_FILE_PATH = "/var/lib/zmirror/cache.yml"
os.makedirs(os.path.dirname(CACHE_FILE_PATH), exist_ok = True)


cache_dict = dict()
config: None
config_dict = dict()

def load_config_for_id(identifier):
  local_config = None
  if identifier in config_dict:
    local_config = config_dict[identifier]
  else:
    log.error(f"id `{identifier}` not found in core.config_dict.")
  return local_config


def entity_id(entity):
  return "|".join((entity.__class__.__name__, entity.id()))

def load_cache():
  global cache_dict#pylint: disable=global-statement
  cache_dict = load_yaml_cache(CACHE_FILE_PATH)
def load_config():
  global config#pylint: disable=global-statement
  config = load_yaml_config(CONFIG_FILE_PATH)
  iterate_content_tree3(config, index_entities, None, config_dict)

def index_entities(entity, parent, dct):
  if hasattr(entity, "parent"):
    entity.parent = parent
  if hasattr(entity, "id"):
    dct[entity_id(entity)] = entity
  return dct


def remove_cache():
  remove_yaml_cache(CACHE_FILE_PATH)

def save_cache():
  save_yaml_cache(cache_dict, CACHE_FILE_PATH)



def iterate_content_tree3(o, fn, parent, strt):
  result = fn(o, parent, strt)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        result = iterate_content_tree3(e, fn, o, result)
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

def find_or_create_zfs_cache_by_vdev_path(cache_dictionary, zpool, vdev_path):
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/disk/by-partlabel/").removeprefix("/dev/")
  return find_or_create_cache(cache_dictionary, ZFSBlockdevCache, pool=zpool, dev=vdev_name)

def get_zpool_status(zpool_name):
  _, zpool_status, _, _ = exec(f"zpool status {zpool_name}")#pylint: disable=exec-used
  return zpool_status

