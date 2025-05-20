



import traceback
import sys
import argparse


from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs, env_var_or
from .entities import *
from . import commands as commands
from .daemon import daemon
from kpyutils.kiify import KdStream

from .user_commands import *

from . import operations as operations


ZMIRROR_CONFIG_PATH_DEFAULT = "/etc/zmirror/zmirror-config.yml"
ZMIRROR_CACHE_PATH_DEFAULT = "/var/lib/zmirror/zmirror-cache.yml"
ZMIRROR_SOCKET_PATH_DEFAULT = "/run/zmirror/zmirror.socket"

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
exec = myexec#pylint: disable=redefined-builtin








def main(args=None):



  parser = argparse.ArgumentParser(prog="zmirror")
  subs = parser.add_subparsers(required=True)


  # nice to have, maybe?: zmirror trigger        # simulates events or something...


  # nice to have: zmirror prune-cache    # called by user
  # prune_parser = subs.add_parser('prune-cache', parents=[], help='remove cache entries that are not also present in config')
  # prune_parser.set_defaults(func=prune_cache)



  shared_parser = argparse.ArgumentParser(add_help=False)

  shared_parser.add_argument("--config-path", type=str, help="the path to the config file", default=env_var_or("ZMIRROR_CONFIG_PATH", ZMIRROR_CONFIG_PATH_DEFAULT))

  shared_parser.add_argument("--cache-path", type=str, help="the path to the cache file", default=env_var_or("ZMIRROR_CACHE_PATH", ZMIRROR_CONFIG_PATH_DEFAULT))

  socket_parser = argparse.ArgumentParser(add_help=False)
  socket_parser.add_argument("--socket-path", type=str, help="the path to the unix socket (used by zmirror.trigger)", default=env_var_or("ZMIRROR_SOCKET_PATH", ZMIRROR_SOCKET_PATH_DEFAULT))
  # shared_parser.add_argument("runtime-dir", type=str, help="the path to the runtime directory", default= "/var/run/zmirror")

  cancel_parser = argparse.ArgumentParser(add_help=False)
  cancel_parser.add_argument("--cancel", action="store_true")

  daemon_parser = subs.add_parser('daemon', parents=[shared_parser, socket_parser], help="starts the zmirror daemon")
  daemon_parser.set_defaults(func=daemon)


  # daemon commands
  # #######################

  clear_cache_parser = subs.add_parser('clear-cache', parents=[socket_parser], help= 'clear cache')
  clear_cache_parser.set_defaults(func=make_send_simple_daemon_command("clear-cache"))


  # zmirror status   # called by user
  status_parser = subs.add_parser('status', parents=[socket_parser], help='show status of zmirror')
  status_parser.set_defaults(func=make_send_simple_daemon_command("status"))

  scrub_all_parser = subs.add_parser('scrub-all', parents=[socket_parser], help='show status of zmirror')
  scrub_all_parser.set_defaults(func=make_send_simple_daemon_command("scrub-all"))

  scrub_overdue_parser = subs.add_parser('scrub-overdue', parents=[socket_parser, cancel_parser], help='show status of zmirror')
  scrub_overdue_parser.set_defaults(func=make_send_simple_daemon_command("scrub-overdue"))


  # scrub_parser = subs.add_parser('scrub-overdue', parents=[], help='scrub devices that have not been scrubbed for too long')
  # scrub_parser.set_defaults(func=scrub)

  online_parser = subs.add_parser('online', parents=[socket_parser], help='online devices')
  offline_parser = subs.add_parser('offline', parents=[socket_parser], help='offline devices')

  online_subs = online_parser.add_subparsers(required=True)
  offline_subs = offline_parser.add_subparsers(required=True)



  def make_onlineable_commands(typ):
    command_name = command_name_for_type[typ]

    common_parser = argparse.ArgumentParser(add_help=False)
    for fld in typ.id_fields(): 
      common_parser.add_argument(f"--{fld}", type=str, required=True)
    
    online = online_subs.add_parser(command_name, parents=[common_parser, cancel_parser])
    online.set_defaults(func=make_send_request_daemon_command(Request.ONLINE, typ))

    offline = offline_subs.add_parser(command_name, parents=[common_parser, cancel_parser])
    offline.set_defaults(func=make_send_request_daemon_command(Request.OFFLINE, typ))
    





  for typ in [Disk, Partition, ZPool, ZFSVolume, DMCrypt, ZDev]:
    make_onlineable_commands(typ)


  def make_scrub_request_command():
    parser = subs.add_parser("scrub", parents=[socket_parser, cancel_parser])
    for fld in ZDev.id_fields():
      parser.add_argument(f"--{fld}", type=str)

    parser.set_defaults(func=make_send_request_daemon_command(Request.SCRUB, ZFSVolume))

  make_scrub_request_command()





  args = parser.parse_args(args=args)

  # if args.cache_path is None:
  #  args.cache_path = args.state_dir + "/cache.yml"

  try:
    args.func(args)
  except Exception as exception:
    traceback.print_exc()
    error_message = str(exception)
    log.error(error_message)

    outs.newlines(3)
    outs.print("error")
    outs.newline()
    outs.print("################")
    outs.newlines(2)
    outs.print(error_message)
    exit(error_message)

  log.info("zmirror finished!")


if __name__ == "__main__":
  main()
