



import os, os.path
import re
from datetime import datetime
import os
import argparse
import dateparser
import traceback
from dataclasses import dataclass
from zmirror_logging import ZMirror_Logger
from ki_utils import *
from zmirror_dataclasses import *
from pyutils import *
from zmirror_utils import *

zmirror_logger = ZMirror_Logger()
log = zmirror_logger.get_Logger()

log.info("starting zmirror")

config_file_path = "/etc/zmirror/config.yml"
cache_file_path = "/var/lib/zmirror/cache.yml"
os.makedirs(os.path.dirname(cache_file_path), exist_ok = True)

command_list = []








#alexTODO: delete this
#def my_constructor(loader, node):
#  return loader.construct_yaml_object(node, Partition)
#alexTODO: delete this END

# zpool scrub eva
# systemctl zfs-auto-scrub-daily.interval


# objects from config
# objects from cache
# for o in config
#    if exists cache obj
#        take data from cache and copy to config


# {:
#   "DM_Crypt:eva-a-main": DM_Crypt
#     ohne content
#     ohne name
#     last-online: 2024...
#

# event
#   which object is concerned?
# for event in config
#
#    find event in cache
#


commands = []


def handle(args):
  global cache_dict
  cache_dict = load_yaml_cache()
  log.info("handling udev and zfs events by interpreting environment variables")
  global env

  now = datetime.now()
  if "ZEVENT_CLASS" in env:
    zevent = env["ZEVENT_SUBCLASS"]
    log.info(f"handling zfs event: {zevent}")
    zpool = env["ZEVENT_POOL"]

    # zpool event
    if zevent in ["scrub_finish", "scrub_start"]:
      zpool_status = get_zpool_status(zpool)

      regex = re.compile(rf'^\s+([a-zA-Z0-9_]+)\s+(ONLINE)\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$')

      for match in regex.finditer(zpool_status):
        dev = match.group(1)

        cache = find_or_create_cache(cache_dict, ZFS_Blockdev_Cache, pool=zpool, dev=dev)
        cache.operation = Since(ZFS_Operation_State.NONE, now)
        if zevent == "scrub_finish":
          cache.last_scrubbed = now
        elif zevent == "scrub_start":
          cache.operation.state = ZFS_Operation_State.SCRUBBING
    # TODO: add to docs that the admin must ensure that zpool import uses /dev/mapper (dm) and /dev/vg/lv (lvm) and /dev/disk/by-partlabel (partition)
      # zpool import -d /dev/mapper -d /dev/vg/lv -d /dev/disk/by-partlabel
      # zpool create my-pool mirror /dev/vg-my-vg/my-lv /dev/disk/by-partlabel/my-partition /dev/mapper/my-dm-crypt

    # zpool-vdev event
    elif zevent in ["vdev_online", "statechange"]:
      # possible cases:
        # ZEVENT_POOL:: mypoolname
        # ZEVENT_VDEV_PATH:: /dev/mapper/mypoolname-b-main
        # ZEVENT_VDEV_PATH:: /dev/{vg_bak_gamma/lv_bak_gamma}
        # ZEVENT:: /dev/{sda3}
        # ZEVENT:: /dev/disk/by-partlabel/mypartlabel
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(cache_dict, zpool, vdev_path)
      if zevent == "vdev_online":
        log.info(f"zdev {cache.pool}:{cache.dev} went online")
        cache.state = Since(ZFS_State.ONLINE, now)
      elif zevent == "statechange":
        if env["ZEVENT_VDEV_STATE_STR"] == "OFFLINE":
          log.info(f"zdev {cache.pool}:{cache.dev} went offline")
          cache.state = Since(ZFS_State.DISCONNECTED, now)
        else:
          log.warning(f"(potential bug) unknown statechange event: {env["ZEVENT_VDEV_STATE_STR"]}")
          cache.state = Since(ZFS_State.UNKNOWN, now)

    # zool-vdev event
    elif zevent in ["resilver_start", "resilver_finish"]:
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(vdev_path)
      cache.operation = Since(ZFS_Operation_State.NONE, now)
      if zevent == "resilver_start":
        cache.operation = Since(ZFS_Operation_State.RESILVERING, now)
      elif zevent == "resilver_finish":
        cache.operation = Since(ZFS_Operation_State.NONE, now)
        cache.last_resilvered = now

  elif ("DEVTYPE" in env):
    action = env["ACTION"]
    devtype = env["DEVTYPE"]
    log.info(f"handling udev block event: {action}")
    if devtype == "disk":
      if "ID_SERIAL" in env:
        cache = find_or_create_cache(cache_dict, Disk, serial=env["ID_SERIAL"])
      elif "DM_NAME" in env:
        cache = find_or_create_cache(cache_dict, Disk, name=env["DM_NAME"])
    elif devtype == "partition":
      cache = find_or_create_cache(cache_dict, Partition, name=env["PARTNAME"])
    if cache != None:
      if action == "add":
        cache.state = Since(DM_Crypt_State.ONLINE, now)
      elif action == "remove":
        cache.state = Since(DM_Crypt_State.DISCONNECTED, now)

  save_cache(cache_dict, cache_file_path)



# zmirror trim-cache






# yaml.dump(config)










# we are overriding python's internal exec, which would execute python code dynamically, because we don't need nor like it

pyexec = exec
exec = myexec


# zmirror scrub
def scrub(args):
  global cache_dict
  cache_dict = load_yaml_cache()
  log.info("starting zfs scrubs if necessary")
  def possibly_scrub(dev):
    if isinstance(dev, ZFS_Blockdev):
      cache = find_or_create_cache(cache_dict, ZFS_Blockdev_Cache, pool=dev.pool, dev=dev.dev)
      if dev.scrub_interval != None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(dev.scrub_interval)
        if (cache.last_scrubbed == None or allowed_delta > cache.last_scrubbed):
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' must be scrubbed")
          if cache.operation != None and cache.operation.state == ZFS_Operation_State.NONE:
            commands.append(f"zpool scrub {dev.pool}")
        else:
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' does not have to be scrubbed")
  zmirror = load_yaml_config(config_file_path=config_file_path)
  iterate_content_tree(zmirror, possibly_scrub)
  execute_commands()


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



def clear_cache(args):
  remove_cache(cache_file_path)


def show_status(args):
  global cache_dict
  cache_dict = load_yaml_cache()
  stream = Kd_Stream(outs)
  # log.info("starting zfs scrubs if necessary")
  def possibly_scrub(dev):
    if isinstance(dev, ZFS_Blockdev):
      cache = find_or_create_cache(cache_dict, ZFS_Blockdev_Cache, pool=dev.pool, dev=dev.dev)
      out = ZFS_Blockdev_Output(pool=dev.pool, dev=dev.dev)
      copy_attrs(cache, out)
      copy_attrs(dev, out)
      stream.print_obj(out)
      stream.stream.newlines(3)
  zmirror = load_yaml_config(config_file_path=config_file_path)
  iterate_content_tree(zmirror, possibly_scrub)

env = dict(os.environ)
#


# Create the parser
parser = argparse.ArgumentParser(description="zmirror")
subparser = parser.add_subparsers()


# nice to have, maybe?: zmirror trigger        # simulates events or something...


# nice to have: zmirror prune-cache    # called by user
# prune_parser = subparser.add_parser('prune-cache', parents=[], help='remove cache entries that are not also present in config')
# prune_parser.set_defaults(func=prune_cache)

clear_cache_parser = subparser.add_parser('clear-cache', parents=[], help= 'clear cache')
clear_cache_parser.set_defaults(func=clear_cache)

# zmirror status   # called by user
status_parser = subparser.add_parser('status', parents=[], help='show status of zmirror')
status_parser.set_defaults(func=show_status)


# zmirror scrub   # called by systemd.timer
scrub_parser = subparser.add_parser('scrub', help='start pending scrubs')
scrub_parser.set_defaults(func=scrub)

# zmirror    # without args
parser.set_defaults(func=handle)

args = parser.parse_args()

try:
  args.func(args)
except Exception as exception:
  traceback.print_exc()
  error_message = str(exception)
  log.error(error_message)

  outs.newlines(3)
  outs.print("error")
  outs.print("################")
  outs.newlines(2)
  outs.print(error_message)
  exit(error_message)

log.info("zmirror finished!")
