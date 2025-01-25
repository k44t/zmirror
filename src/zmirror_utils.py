from pyutils import *
from zmirror_dataclasses import *
from zmirror_logging import log



log.info("starting zmirror")

config_file_path = "/etc/zmirror/config.yml"
cache_file_path = "/var/lib/zmirror/cache.yml"
os.makedirs(os.path.dirname(cache_file_path), exist_ok = True)



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
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/")
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
