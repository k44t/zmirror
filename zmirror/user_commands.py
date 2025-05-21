
import socket
import dateparser

from zmirror.entities import init_config, iterate_content_tree, remove_cache

from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs, require_path
from . import commands as commands
from kpyutils.kiify import KdStream

import argparse
import sys
import logging
import inspect
import json
import codecs
import traceback


def daemon_request(request, cancel, typ, ids):

  constructor_params = inspect.signature(typ).parameters

  # Filter the Namespace to include only the required arguments
  filtered_args = {k: v for k, v in ids.items() if k in constructor_params}
  entity = config.find_config(typ, **filtered_args)
  if entity is None:
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: entity not configured")
    return
  if entity.request(request, unschedule=cancel):
    config.last_request_at = datetime.now()
  else:
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
    if isinstance(entity, ZDev):
      if Request.SCRUB not in entity.requested:
        entity.request(Request.SCRUB)
  iterate_content_tree(config.config_root, do)

def handle_trim_all_command():
  def do(entity):
    if isinstance(entity, ZDev):
      if Request.TRIM not in entity.requested:
        entity.request(Request.TRIM)
  iterate_content_tree(config.config_root, do)



def handle_scrub_overdue_command():
  def do(entity):
    if isinstance(entity, ZDev):
      cache = cached(entity)
      if entity.scrub_interval is not None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(entity.scrub_interval)
        # this means that allowed_delta is a timestamp in the past


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
    elif name == "scrub-all":
      handle_scrub_all_command()
    elif name == "scrub-overdue":
      handle_scrub_overdue_command()
    elif name == "trim-all":
      handle_trim_all_command()
    elif name == "online-all":
      handle_online_all_command(command)
    elif name == "maintenance":
      handle_online_all_command(command)
    else:
      handle_request_command(command)
  except Exception as ex:
    log.error("failed to handle command")
    log.error(f"exception : {traceback.format_exc()} --- {str(ex)}")
    # scrub_parser.set_defaults(func=request_scrub_all_overdue)
  finally:
    log.removeHandler(handler)



command_name_for_type = {
  Disk: "disk",
  Partition: "partition",
  ZPool: "zpool",
  ZDev: "zdev",
  ZFSVolume: "zfs-volume",
  DMCrypt: "dm-crypt"
}

type_for_command_name = {value: key for key, value in command_name_for_type.items()}

request_for_name = {
  "online": Request.ONLINE,
  "offline": Request.OFFLINE,
  "scrub": Request.SCRUB,
  "trim": Request.SCRUB
}

name_for_request = {value: key for key, value in request_for_name.items()}

def make_send_daemon_wrapper(fn):
  def do(args):
    path = args.socket_path
    delattr(args, "socket_path")
    delattr(args, "func")
    command = fn(args)
    log.debug("sending command:")
    log.debug(command)
  
    require_path(path, "no zmirror socket at")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as con:

      try:
        # Connect the socket to the path where the server is listening
        con.connect(path)
        decoder = codecs.getincrementaldecoder('utf-8')()

        # Send data
        message = json.dumps({"ZMIRROR_COMMAND": command}, indent=4)
        con.sendall(f"{len(message)}:{message}".encode('utf-8'))
        
        while True:
          data = con.recv(4096)
          if not data:
              break
          decoded_data = decoder.decode(data, final=False)
          sys.stdout.write(decoded_data)
          sys.stdout.flush()
        remaining_data = decoder.decode(b'', final=True)
        sys.stdout.write(remaining_data)
        sys.stdout.flush()
      except KeyboardInterrupt: #pylint: disable=try-except-raise
        raise
      except Exception as ex:
        log.error(f"communication error: {ex}")
  return do


def make_send_simple_daemon_command(command):
  def do(args):
    r = {"command": command}
    for k, v in vars(args).items():
      r[k] = v
    return r
  return make_send_daemon_wrapper(do)


def make_send_request_daemon_command(request, typ):
  def do(args):

    r = {
      "command": name_for_request[request]
    }

    if args.cancel:
      r["cancel"] = "yes"

    delattr(args, "cancel")
    r["type"] = command_name_for_type[typ]
    r["identifiers"] = vars(args)

    return r
  return make_send_daemon_wrapper(do)

