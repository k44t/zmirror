from pyutils import *
from zmirror_dataclasses import *
from zmirror_logging import log



log.info("starting zmirror")

config_file_path = "/etc/zmirror/config.yml"
cache_file_path = "/var/lib/zmirror/cache.yml"
os.makedirs(os.path.dirname(cache_file_path), exist_ok = True)


cache_dict = dict()
config: ZMirror = None
config_dict = dict()

def load_config_for_id(id):
  global config_dict
  config = None
  if id in config_dict:
    config = config_dict[id]
  else:
    log.error(f"id `{id}` not found in core.config_dict.")
  return config


def entity_id(entity):
  return "|".join((entity.__class__.__name__, entity.id()))

def load_cache():
  global cache_dict
  cache_dict = load_yaml_cache(cache_file_path)
def load_config():
  global config
  config = load_yaml_config(config_file_path)
  iterate_content_tree3(config, index_entities, None, config_dict)

def index_entities(entity, parent, dct):
  if hasattr(entity, "id"):
    dct[entity_id(entity)] = entity
  if hasattr(entity, "parent"):
    entity.parent = parent


def remove_cache():
  remove_yaml_cache()

def save_cache():
  save_yaml_cache(cache_dict, cache_file_path)



def iterate_content_tree3(o, fn, parent, strt):
  result = fn(o, parent, strt)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        result = iterate_content_tree3(e, fn, result)
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
  if fresult != None:
    result.append(o)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        rlst = iterate_content_tree(e, fn)
        result = result + rlst
  return result

def find_or_create_zfs_cache_by_vdev_path(cache_dict, zpool, vdev_path):
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/disk/by-partlabel/").removeprefix("/dev/")
  return find_or_create_cache(cache_dict, ZFS_Blockdev_Cache, pool=zpool, dev=vdev_name)

def get_zpool_status(zpool_name):
  returncode, zpool_status, formatted_response, formatted_error = exec(f"zpool status {zpool_name}")
  return zpool_status



commands = []

def add_command(command):
  commands.append(command)


def execute_commands():
  seen = set()                                                    
  cmds = [x for x in commands if not (x in seen or seen.add(x))]

  for cmd in cmds:
    execute_command(cmd)

def execute_command(command):
  apply_commands = False
  if apply_commands:
    log.info(f"executing command: {command}")
    returncode, formatted_output, formatted_response, formatted_error = exec(command)
    if returncode != 0:
      currently_scrubbing = False
      for line in formatted_output:
        if "currently scrubbing" in line:
          info_message = line
          log.info(info_message)
          currently_scrubbing = True
      if not currently_scrubbing:
        error_message = f"something went wrong while executing command {command}, terminating script now"
        log.error(error_message)
        exit(error_message)
    log.info(formatted_output)
  else:
    warning_message = f"applying command '{command}' is currently turned off!"
    log.warning(warning_message)
