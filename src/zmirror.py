



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
from zmirror_socket import *


from zmirror_logging import log



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


daemon_parser = subparser.add_parser('daemon', help="starts the zmirror daemon")
daemon_parser.set_defaults(func=daemon)


# starts a daemon, or rather a service, or maybe it should be called simply a server, a listening loop that listens to whatever is being sent on a unix socket: /var/run/zmirror/zmirror.socket, to which zmirror-udev and zmirror-zed send their event streams. 
# these scripts connect to it, send a set of environment variables and then disconnect.
# this service then reads those environment variables
# and creates event objects 
# inside a list that is thread safe (only one thread ever changes the list)
# the code doing all the above should be in zmirror-server.py
def start_daemon(args):
  pass
# on the other side, in a different thread (another loop)
# this daemon simply removes the events from the list in order (FIFO)
#
# the code for this should be largely will lay in zmirror-handler.py:
# and handles the events
# and by handling we mean for now, that they simply get logged
# so this is just a description for the next milestone


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
