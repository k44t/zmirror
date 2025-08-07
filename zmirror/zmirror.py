



import traceback
import sys
import argparse


from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs, env_var_or
from .entities import *
from . import commands as commands
from .daemon import daemon
from kpyutils.kiify import KdStream, date_or_datetime

from .user_commands import *

from . import operations as operations

from .defaults import *

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
  parser.add_argument('--version', action='version', version=f'zmirror {VERSION}')
  subs = parser.add_subparsers(required=True)


  # nice to have, maybe?: zmirror trigger        # simulates events or something...


  # nice to have: zmirror prune-cache    # called by user
  # prune_parser = subs.add_parser('prune-cache', parents=[], help='remove cache entries that are not also present in config')
  # prune_parser.set_defaults(func=prune_cache)

  shared_parser = argparse.ArgumentParser(add_help=False)

  shared_parser.add_argument("--config-path", type=str, help=f"the path to the config file. May be set via the environment variable `ZMIRROR_CONFIG_PATH`. Defaults to `{ZMIRROR_CONFIG_PATH_DEFAULT}`", default=env_var_or("ZMIRROR_CONFIG_PATH", ZMIRROR_CONFIG_PATH_DEFAULT))

  shared_parser.add_argument("--cache-path", type=str, help=f"the path to the cache file in which zmirror stores device state. May be set via the environment variable `ZMIRROR_CACHE_PATH`. Defaults to `{ZMIRROR_CACHE_PATH_DEFAULT}`", default=env_var_or("ZMIRROR_CACHE_PATH", ZMIRROR_CACHE_PATH_DEFAULT))

  socket_parser = argparse.ArgumentParser(add_help=False)
  socket_parser.add_argument("--socket-path", type=str, help=f"the path to the unix socket on which `zmirror daemon` listens, to which `zmirror-trigger` sends UDEV and ZED events, and to which commands are sent when you invoke `zmirror <command>`. May be set via the environment variable `ZMIRROR_SOCKET_PATH`. Defaults to `{ZMIRROR_SOCKET_PATH_DEFAULT}`", default=env_var_or("ZMIRROR_SOCKET_PATH", ZMIRROR_SOCKET_PATH_DEFAULT))

  # shared_parser.add_argument("runtime-dir", type=str, help="the path to the runtime directory", default= "/var/run/zmirror")

  cancel_parser = argparse.ArgumentParser(add_help=False)
  cancel_parser.add_argument("--cancel", action="store_true")

  daemon_parser = subs.add_parser('daemon', parents=[shared_parser, socket_parser], help="starts zmirror in daemon mode")
  daemon_parser.set_defaults(func=daemon)


  # daemon commands
  # #######################


  def subcmd(command, help=None, cancel=False):
    parents = [socket_parser]
    if cancel:
      parents.append(cancel_parser)
    subpsr = subs.add_parser(command, parents=parents, help=help)
    subpsr.set_defaults(func=make_send_simple_daemon_command(command))


  subcmd("clear-cache", help="clears the cache and removes the cache file (which stores the dates of when the maintenance tasks were last run). Triggers a configuration reload.")
  subcmd("reload-config", help="reloads the configuration.")

  subcmd("scrub-all", cancel=True, help="requests all configured zdevs to be scrubbed. This will bring all necessary and available parent devices (i.e. dm-crypts) online.")
  subcmd("scrub-overdue", help="requests zdevs to be scrubbed if they are behind their configured scrub_interval. This will bring all necessary and available parent devices (i.e. dm-crypts) online.")

  subcmd("resilver-overdue", help="requests zdevs to be resilvered if they are behind their configured resilver_interval. Since a resilver happens whenever a mirrored device is brought online, this really does nothing but (try to) online the respective devices.")

  subcmd("trim-all", cancel=True, help="requests all configured zdevs to be trimmed. This will bring all necessary and available parent devices (i.e. dm-crypts) online.")
  subcmd("trim-overdue", help="requests zdevs to be trimmed if they are behind their configured trim_interval. This will bring all necessary and available parent devices (i.e. dm-crypts) online.")


  subcmd("online-all", cancel=True, help="requests all configured devices to be onlined.")

  subcmd("status-all", help="shows the status of all configured devices")
  subcmd("daemon-version", help="shows the version of the (currently running) zmirror daemon")

  subcmd("maintenance", help="triggers all maintenance tasks (scrub and trim as scheduled as well as onlining devices that should be brought up to date [resilvered]). This is what you want to schedule via a cronjob or a systemd timer. It makes sense to do this at night on a weekday where there is not much load on your machine. This will online all devices that are present and need maintenance. The devices will only be taken offline afterwards if you have configured the respective event timers to take them offline (i.e. `on_resilvered` set to `offline`).")


  # scrub_parser = subs.add_parser('scrub-overdue', parents=[], help='scrub devices that have not been scrubbed for too long')
  # scrub_parser.set_defaults(func=scrub)

  online_parser = subs.add_parser('online', parents=[socket_parser], help='request device to go online')
  offline_parser = subs.add_parser('offline', parents=[socket_parser], help='request device to go offline')
  status_parser = subs.add_parser('status', parents=[socket_parser], help='show device status')
  trim_parser = subs.add_parser('trim', parents=[socket_parser], help='request device trim')

  online_subs = online_parser.add_subparsers(required=True)
  offline_subs = offline_parser.add_subparsers(required=True)
  status_subs = status_parser.add_subparsers(required=True)
  trim_subs = trim_parser.add_subparsers(required=True)

  scrub_parser = subs.add_parser("scrub", parents=[socket_parser, cancel_parser], help="request device to be scrubbed")
  scrub_subs = scrub_parser.add_subparsers(required=True)



  enable_subs = subs.add_parser('enable', parents=[socket_parser], help='enable zmirror daemon property').add_subparsers(required=True)
  disable_subs = subs.add_parser('disable', parents=[socket_parser], help='disable zmirror daemon property').add_subparsers(required=True)
  set_subs = subs.add_parser('set', parents=[socket_parser], help='set zmirror daemon property to value').add_subparsers(required=True)
  get_subs = subs.add_parser('get', parents=[socket_parser], help='get zmirror daemon property value').add_subparsers(required=True)

  def add_enable_disable_parsers(name, help=None):
    enable_parser = enable_subs.add_parser(name, help=f"enable {help}")
    disable_parser = disable_subs.add_parser(name, help=f"disable {help}")

    enable_parser.set_defaults(func=make_send_set_property_daemon_command(name, "yes"))
    disable_parser.set_defaults(func=make_send_set_property_daemon_command(name, "no"))


    get_subs.add_parser(name, help=f"get {help}").set_defaults(func=make_send_get_property_daemon_command(name))

  add_enable_disable_parsers("commands", help="command execution")
  add_enable_disable_parsers("log-events", help="logging of all UDEV and ZED events received by zmirror")


  def add_set_property_parser(name, set_help=None, get_help=None):
    set_parser = set_subs.add_parser(name, help=set_help)
    set_parser.add_argument("value", type=str)
    set_parser.set_defaults(func=make_send_set_property_daemon_command(name))
    get_subs.add_parser(name, help=get_help).set_defaults(func=make_send_get_property_daemon_command(name))

  add_set_property_parser("log-level", "set log level to one of: trace | debug | verbose | info | warning | error | critical")
  add_set_property_parser("timeout", "set request timeout in seconds")

  def make_onlineable_commands(typ):
    command_name = command_name_for_type[typ]

    common_parser = argparse.ArgumentParser(add_help=False)
    for fld in typ.id_fields():
      common_parser.add_argument(f"{fld}", type=str, default=None)
    
    online = online_subs.add_parser(command_name, parents=[common_parser, cancel_parser])
    online.set_defaults(func=make_send_request_daemon_command(RequestType.ONLINE, typ))

    if typ in {ZDev}:
      trim = trim_subs.add_parser(command_name, parents=[common_parser, cancel_parser])
      trim.set_defaults(func=make_send_request_daemon_command(RequestType.TRIM, typ))

    offline = offline_subs.add_parser(command_name, parents=[common_parser, cancel_parser])
    offline.set_defaults(func=make_send_request_daemon_command(RequestType.OFFLINE, typ))

    status = status_subs.add_parser(command_name, parents=[common_parser])
    status.set_defaults(func=make_send_entity_daemon_command("status", typ))

    if typ in [ZDev, ZPool]:

      scrub = scrub_subs.add_parser(command_name, parents=[common_parser])
      scrub.set_defaults(func=make_send_request_daemon_command(RequestType.SCRUB, typ))




  for typ in [Disk, Partition, ZPool, ZFSVolume, DMCrypt, ZDev]:
    make_onlineable_commands(typ)







  args = parser.parse_args(args=args)

  # if args.cache_path is None:
  #  args.cache_path = args.state_dir + "/cache.yml"

  try:
    args.func(args)
  except Exception as exception:
    error_message = str(exception)
    log.error(error_message)
    traceback.print_exc()



if __name__ == "__main__":
  main()
