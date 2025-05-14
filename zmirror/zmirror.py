



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

from . import operations as operations




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


# zmirror scrub
def scrub(args):#pylint: disable=unused-argument
  init_config(config_path=args.config_path, cache_path=args.cache_path)
  operations.scrub_all_overdue()
  commands.execute_commands()






def clear_cache(args):#pylint: disable=unused-argument
  remove_cache(args.cache_path)




def show_status(args):#pylint: disable=unused-argument
  init_config(cache_path=args.cache_path, config_path = args.config_path)
  stream = KdStream(outs)
  # log.info("starting zfs scrubs if necessary")
  def show(dev):
    stream.print_obj(cached(dev).cache)
    
  iterate_content_tree(config.config_root, show)





def main(args=None):

  parser = argparse.ArgumentParser(prog="zmirror")
  subparser = parser.add_subparsers(required=True)


  # nice to have, maybe?: zmirror trigger        # simulates events or something...


  # nice to have: zmirror prune-cache    # called by user
  # prune_parser = subparser.add_parser('prune-cache', parents=[], help='remove cache entries that are not also present in config')
  # prune_parser.set_defaults(func=prune_cache)



  shared_parser = argparse.ArgumentParser(add_help=False)

  shared_parser.add_argument("--config-path", type=str, help="the path to the config file", default=env_var_or("ZMIRROR_CONFIG_PATH", "./zmirror-config.yml"))

  shared_parser.add_argument("--cache-path", type=str, help="the path to the cache file", default=env_var_or("ZMIRROR_CACHE_PATH", "./zmirror-cache.yml"))

  shared_parser.add_argument("--socket-path", type=str, help="the path to the unix socket (used by zmirror.trigger)", default=env_var_or("ZMIRROR_SOCKET_PATH", "./zmirror.socket"))
  # shared_parser.add_argument("runtime-dir", type=str, help="the path to the runtime directory", default= "/var/run/zmirror")


  clear_cache_parser = subparser.add_parser('clear-cache', parents=[shared_parser], help= 'clear cache')
  clear_cache_parser.set_defaults(func=clear_cache)


  daemon_parser = subparser.add_parser('daemon', parents=[shared_parser], help="starts the zmirror daemon")
  daemon_parser.set_defaults(func=daemon)




  # zmirror status   # called by user
  status_parser = subparser.add_parser('status', parents=[shared_parser], help='show status of zmirror')
  status_parser.set_defaults(func=show_status)


  # zmirror scrub   # called by systemd.timer
  scrub_parser = subparser.add_parser('scrub', parents=[shared_parser], help='start pending scrubs')
  scrub_parser.set_defaults(func=scrub)

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
