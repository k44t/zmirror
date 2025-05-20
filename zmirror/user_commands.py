
import dateparser

from zmirror.entities import init_config, iterate_content_tree, remove_cache

from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs
from . import commands as commands
from kpyutils.kiify import KdStream

import argparse
import sys
import logging
import inspect



def daemon_request(request, cancel, typ, kwargs):
  constructor_params = inspect.signature(typ).parameters

  # Filter the Namespace to include only the required arguments
  filtered_args = {k: v for k, v in kwargs if k in constructor_params}
  entity = config.find_config(typ, **filtered_args)
  if entity is None:
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: entity not configured")
    return
  if not entity.request(request, unschedule=cancel):
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: request {request} failed. See previous error messages.")
    return
  log.info(f"{make_id_string(make_id(typ, **filtered_args))}: requested {request} scheduled successfully")



def handle_request_command(command):
  name = command["command"]
  if not name in request_for_name:
    raise ValueError(f"unknown command {name}")
    
  request = request_for_name[name]
  if "cancel" in command:
    cancel = yes_no_absent_or_dict(command, "cancel", False, "error")
  else:
    cancel = False
  if not "type" in command:
    raise ValueError(f"missing type for handling command: {name}")
 
  type_name = command["type"]
  if not type_name in type_for_command_name:
    raise ValueError(f"unknown type: {type_name}")
  typ = type_for_command_name[type_name]
  if not "identifiers" in command:
    raise ValueError(f"no identifiers given for type: {typ}")
  ids = command["identifiers"]
  if not isinstance(ids, dict):
    raise ValueError("identifiers are not a dict of type {{str:str}}")
  daemon_request(request, cancel, typ, ids)



def handle_status_command(out):
   
  stream = KdStream(out)
  # log.info("starting zfs scrubs if necessary")
  def do(entity):
    stream.print_obj(cached(entity).cache)
    
  iterate_content_tree(config.config_root, do)



def handle_clear_cache_command():

  log.info("clearing cache")
  
  remove_cache(config.cache_path)

  log.info("cache cleared")

  handle_reload_command()



def handle_reload_command():

  log.info("reloading configuration")

  init_config(config.cache_path, config.config_path)

  log.info("configuration reloaded")



def handle_scrub_all_command():
  def do(entity):
    if isinstance(entity, ZFSBackingDevice):
      if Request.SCRUB not in entity.requested:
        entity.request(Request.SCRUB)
  iterate_content_tree(config.config_root, do)



def handle_scrub_overdue_command():
  def do(entity):
    if isinstance(entity, ZFSBackingDevice):
      cache = cached(entity)
      if entity.scrub_interval is not None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(entity.scrub_interval)
        if (cache.last_scrubbed is None or allowed_delta > cache.last_scrubbed):
          if Request.SCRUB not in entity.requested:
            log.info(f"{entity_id_string(entity)}: requesting scrub")
            entity.request(Request.SCRUB)
          else:
            log.debug(f"{entity_id_string(entity)}: scrub already requested")
        else:
          log.info(f"{entity_id_string(entity)}: scrub not yet overdue, skipping")
      else:
        log.info(f"{entity_id_string(entity)}: no scrub interval configured, skipping")
  iterate_content_tree(config.config_root, do)



def handle_online_all_command(command):
  def do(entity):
    if Request.ONLINE not in entity.requested:
      entity.request(Request.ONLINE, unrequest=yes_no_absent_or_dict(command, "cancel", False, "error"))
  iterate_content_tree(config.config_root, do)



def handle_command(command, stream):
  handler = logging.StreamHandler(stream)
  log.addHandler(handler)
  try:
    name = command["command"]
    if name == "status":
       handle_status_command(stream)
    elif name == "clear-cache":
       handle_clear_cache_command()
    elif name == "scrub":
      if yes_no_absent_or_dict(command, "all", False, "error"):
        handle_scrub_all_command()
      elif yes_no_absent_or_dict(command, "overdue", False, "error"):
        handle_scrub_overdue_command()
      else:
        handle_request_command(command)
    elif name == "online":
      if yes_no_absent_or_dict(command, "all", False, "error"):
        handle_online_all_command(command)
      else:
        handle_request_command(command)
    else:
       handle_request_command(command)
  except Exception as ex:
    log.error(f"failed to handle command: {ex}")
    # scrub_parser.set_defaults(func=request_scrub_all_overdue)
  finally:
    log.removeHandler(handler)



command_name_for_type = {
  Disk: "disk",
  Partition: "partition",
  ZPool: "zpool",
  ZFSBackingDevice: "zfs-backing-device",
  ZFSVolume: "zfs-volume",
  DMCrypt: "dm-crypt"
}

type_for_command_name = {value: key for key, value in command_name_for_type.items()}

request_for_name = {
  "online": Request.ONLINE,
  "offline": Request.OFFLINE,
  "scrub": Request.SCRUB
}
