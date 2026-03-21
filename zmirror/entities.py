import os
from datetime import datetime
import re
import logging
from typing import Optional

from .util import init_cache_db, load_yaml_config, remove_cache_db, require_path
from .util import myexec as myexec #pylint: disable=redefined-builtin
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
  log.info(f"loading config from: {config_path}")
  config.config_root = load_yaml_config(config_path)

  config.set_log_level(config.config_root.log_level)
  log.info(f"log-level: {config.name_for_log_level[config.log_level]}")


  config.timeout = int(config.config_root.timeout)

  config.log_events = config.config_root.log_events



  cache_parent = os.path.dirname(cache_path)
  if cache_parent:
    os.makedirs(cache_parent, exist_ok = True)
  log.info(f"loading cache from: {cache_path}") 
  config.cache_dict = dict()
  cache_entities = load_cache(cache_path)
  if cache_entities:
    for cache in cache_entities:
      config.cache_dict[entity_id_string(cache)] = cache
    
  config.config_dict = dict()
  config.lvm_physical_volumes = dict()
  config.zfs_blockdevs = dict()
    

  config.find_config = find_config

  log.info("loading initial state...")

  iterate_content_tree3(config.config_root, index_entities, None, None)
  iterate_content_tree3_depth_first(config.config_root, load_initial_state, None, None)
  iterate_content_tree3_depth_first(config.config_root, update_initial_state, None, None)

  iterate_content_tree3(config.config_root, finalize_init, None, None)

  config.commands_enabled = config.config_root.enable_commands
  log.info(f"command execution enabled: {to_yes(config.commands_enabled)}")

  config.event_handlers_enabled = config.config_root.enable_event_handlers
  log.info(f"event handlers enabled: {to_yes(config.event_handlers_enabled)}")

  commands.execute_commands()

  log.info("configuration initialized")

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
  rcode, zpool_status, _, _ = myexec(command)#pylint: disable=exec-used
  if rcode == 0:
    return "\n".join(zpool_status)
  else:
    logfn(error)
    return None
  
def get_zfs_volume_mode(zfs_path):
  return simple_string_command(f"zfs get volmode {zfs_path} -o value -H", f"failed to get volmode of zfs volume {zfs_path}", log.debug)
  
def get_zfs_mounted(zfs_path):
  return simple_string_command(f"zfs get mounted {zfs_path} -o value -H", f"failed to get volmode of zfs volume {zfs_path}", log.debug)



def remove_cache(cache_path):
  remove_cache_db(cache_path)


def datetime_to_str(value: Optional[datetime]):
  if value is None:
    return None
  return value.isoformat(sep=" ")


def parse_datetime(value):
  if value is None:
    return None
  return datetime.fromisoformat(value)


def parse_cache_identifier(identifier):
  parts = identifier.split("|")
  typ = None
  type_name = parts[0]
  if type_name in TYPE_FOR_NAME:
    typ = get_type_for_name(type_name)
  else:
    for tp in NAME_FOR_TYPE:
      if tp is not None and tp.__name__ == type_name:
        typ = tp
        break
  if typ is None:
    raise ValueError(f"unknown cache type: {type_name}")
  kwargs = dict()
  for part in parts[1:]:
    if ":" in part:
      key, value = part.split(":", 1)
      kwargs[key] = value
  return typ, kwargs


def cache_from_identifier(identifier):
  typ, kwargs = parse_cache_identifier(identifier)
  return typ(**kwargs)


def copy_cache_fields(source, target):
  state_what = source.get("state_what")
  if state_what is not None and hasattr(target, "state"):
    target.state = Since(EntityState[state_what], parse_datetime(source.get("state_since")))

  for attr in ["last_online", "last_update", "last_trim", "last_scrub"]:
    if hasattr(target, attr):
      setattr(target, attr, parse_datetime(source.get(attr)))

  if hasattr(target, "operations"):
    target.operations = []
    for what, since in source.get("operations", []):
      if what in Operation.__members__:
        target.operations.append(Since(Operation[what], parse_datetime(since)))


def is_sqlite_file(path):
  if not os.path.exists(path):
    return False
  try:
    with open(path, "rb") as stream:
      return stream.read(16) == b"SQLite format 3\x00"
  except Exception:
    return False


def load_cache(cache_path):
  if os.path.exists(cache_path) and not is_sqlite_file(cache_path):
    raise ValueError(f"cache file is not a sqlite database: {cache_path}")

  cache_list = []

  conn = init_cache_db(cache_path)
  try:
    op_rows = conn.execute("SELECT entity_id, what, since FROM cache_operations")
    operations_by_entity = dict()
    for entity_id, what, since in op_rows:
      if entity_id not in operations_by_entity:
        operations_by_entity[entity_id] = []
      operations_by_entity[entity_id].append((what, since))

    rows = conn.execute("""
      SELECT id, state_what, state_since, last_online, last_update, last_trim, last_scrub
      FROM cache_entries
    """)
    for identifier, state_what, state_since, last_online, last_update, last_trim, last_scrub in rows:
      try:
        cache = cache_from_identifier(identifier)
      except Exception as ex:
        log.warning(f"failed to load cache entry {identifier}: {ex}")
        continue

      copy_cache_fields({
        "state_what": state_what,
        "state_since": state_since,
        "last_online": last_online,
        "last_update": last_update,
        "last_trim": last_trim,
        "last_scrub": last_scrub,
        "operations": operations_by_entity.get(identifier, [])
      }, cache)
      cache_list.append(cache)
  finally:
    conn.close()

  return cache_list


def save_cache_entries(conn, cache_id, cache):
  state_what = None
  state_since = None
  if hasattr(cache, "state") and cache.state is not None and cache.state.what is not None:
    state_what = cache.state.what.name
    state_since = datetime_to_str(cache.state.when)

  values = {
    "id": cache_id,
    "state_what": state_what,
    "state_since": state_since,
    "last_online": datetime_to_str(getattr(cache, "last_online", None)),
    "last_update": datetime_to_str(getattr(cache, "last_update", None)),
    "last_trim": datetime_to_str(getattr(cache, "last_trim", None)),
    "last_scrub": datetime_to_str(getattr(cache, "last_scrub", None)),
  }

  conn.execute("""
    INSERT INTO cache_entries(id, state_what, state_since, last_online, last_update, last_trim, last_scrub)
    VALUES(:id, :state_what, :state_since, :last_online, :last_update, :last_trim, :last_scrub)
    ON CONFLICT(id) DO UPDATE SET
      state_what = excluded.state_what,
      state_since = excluded.state_since,
      last_online = excluded.last_online,
      last_update = excluded.last_update,
      last_trim = excluded.last_trim,
      last_scrub = excluded.last_scrub
    WHERE
      cache_entries.state_what IS NOT excluded.state_what OR
      cache_entries.state_since IS NOT excluded.state_since OR
      cache_entries.last_online IS NOT excluded.last_online OR
      cache_entries.last_update IS NOT excluded.last_update OR
      cache_entries.last_trim IS NOT excluded.last_trim OR
      cache_entries.last_scrub IS NOT excluded.last_scrub
  """, values)


def save_cache_operations(conn, cache_id, cache):
  if not hasattr(cache, "operations"):
    conn.execute("DELETE FROM cache_operations WHERE entity_id = ?", (cache_id,))
    return

  desired = dict()
  for operation in cache.operations:
    desired[operation.what.name] = datetime_to_str(operation.when)

  existing_rows = conn.execute(
    "SELECT what, since FROM cache_operations WHERE entity_id = ?",
    (cache_id,)
  ).fetchall()
  existing = {what: since for what, since in existing_rows}

  if desired == existing:
    return

  for what, since in desired.items():
    conn.execute("""
      INSERT INTO cache_operations(entity_id, what, since)
      VALUES (?, ?, ?)
      ON CONFLICT(entity_id, what) DO UPDATE SET
        since = excluded.since
      WHERE cache_operations.since IS NOT excluded.since
    """, (cache_id, what, since))

  existing_what = set(existing.keys())
  desired_what = set(desired.keys())
  removed = existing_what - desired_what
  for what in removed:
    conn.execute(
      "DELETE FROM cache_operations WHERE entity_id = ? AND what = ?",
      (cache_id, what)
    )


def save_cache_db(cache_dict, cache_path):
  log.verbose("writing cache")
  conn = init_cache_db(cache_path)
  try:
    with conn:
      ids = list(cache_dict.keys())
      if ids:
        placeholders = ",".join("?" for _ in ids)
        conn.execute(f"DELETE FROM cache_entries WHERE id NOT IN ({placeholders})", ids)
      else:
        conn.execute("DELETE FROM cache_entries")

      for cache_id, cache in cache_dict.items():
        save_cache_entries(conn, cache_id, cache)
        save_cache_operations(conn, cache_id, cache)
  finally:
    conn.close()
  log.debug("cache written.")




cache_save_timer = None

# the cache is only saved every 
def save_cache():
  global cache_save_timer
  if cache_save_timer is None:
    def action():
      global cache_save_timer
      # if config.cache_dict is None:
      #  raise ValueError("init() was not called")
      save_cache_now()
      cache_save_timer = None
    cache_save_timer = start_event_queue_timer(config.cache_save_timeout, action)


def save_cache_now():
  save_cache_db(config.cache_dict, config.cache_path)


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
config.get_zfs_mounted = get_zfs_mounted
