



import traceback
import sys
import argparse
import dateparser
from zmirror_logging import log
from zmirror_dataclasses import ZFSBlockdev, ZFSBlockdevCache, ZFSOperationState, ZFSBlockdevOutput
from pyutils import myexec, outs, copy_attrs
from zmirror_utils import load_yaml_cache, load_yaml_config, find_or_create_cache, iterate_content_tree, remove_cache
import zmirror_utils
import zmirror_commands as commands
from zmirror_daemon import daemon
from ki_utils import KdStream





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
  cache_dictionary = load_yaml_cache(zmirror_utils.CACHE_FILE_PATH)
  log.info("starting zfs scrubs if necessary")
  def possibly_scrub(dev):
    if isinstance(dev, ZFSBlockdev):
      cache = find_or_create_cache(cache_dictionary, ZFSBlockdevCache, pool=dev.pool, dev=dev.dev)
      if dev.scrub_interval is not None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(dev.scrub_interval)
        if (cache.last_scrubbed is None or allowed_delta > cache.last_scrubbed):
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' must be scrubbed")
          if cache.operation is not None and cache.operation.state == ZFSOperationState.NONE:
            commands.add_command(f"zpool scrub {dev.pool}")
        else:
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' does not have to be scrubbed")
  zmirror = load_yaml_config(config_file_path=zmirror_utils.CONFIG_FILE_PATH)
  iterate_content_tree(zmirror, possibly_scrub)
  commands.execute_commands()






def clear_cache(args):#pylint: disable=unused-argument
  remove_cache()




def show_status(args):#pylint: disable=unused-argument
  cache_dict = load_yaml_cache(zmirror_utils.CACHE_FILE_PATH)
  stream = KdStream(outs)
  # log.info("starting zfs scrubs if necessary")
  def show(dev):
    if isinstance(dev, ZFSBlockdev):
      cache = find_or_create_cache(cache_dict, ZFSBlockdevCache, pool=dev.pool, dev=dev.dev)
      out = ZFSBlockdevOutput(pool=dev.pool, dev=dev.dev)
      copy_attrs(cache, out)
      copy_attrs(dev, out)
      stream.print_obj(out)
      stream.stream.newlines(3)
  zmirror = load_yaml_config(config_file_path=zmirror_utils.CONFIG_FILE_PATH)
  iterate_content_tree(zmirror, show)


def testufcntionr():
  test = 1
  print(test)
  print("hello")


def run_command(args):

  parser = argparse.ArgumentParser(description="zmirror")
  subparser = parser.add_subparsers(required=True)


  # nice to have, maybe?: zmirror trigger        # simulates events or something...


  # nice to have: zmirror prune-cache    # called by user
  # prune_parser = subparser.add_parser('prune-cache', parents=[], help='remove cache entries that are not also present in config')
  # prune_parser.set_defaults(func=prune_cache)



  shared_parser = argparse.ArgumentParser(add_help=False)
  shared_parser.add_argument("--config-file", type=str, help="the path to the config file", default= "/etc/zmirror/config.yml")
  shared_parser.add_argument("--state-dir", type=str, help="the path to the state directory", default= "/var/lib/zmirror")
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

  args = parser.parse_args()

  zmirror_utils.CACHE_FILE_PATH = args.state_dir + "/cache.yml"
  zmirror_utils.CONFIG_FILE_PATH = args.config_file

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


if __name__ == "__main__":
  run_command(sys.argv)
