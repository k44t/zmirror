
import socket
import dateparser

from zmirror.defaults import VERSION
from zmirror.entities import *
from . import config
from .config import *

from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs, require_path
from . import commands as commands
from kpyutils.kiify import KdStream, is_yes_or_true, to_yes

import argparse
import sys
import logging
import inspect
import json
import codecs
import traceback




def request(rqst, typ, enactment_level = sys.maxsize, **identifiers):
  tid = make_id_string(make_id(typ, **identifiers))
  entity = load_config_for_id(tid)
  if entity is None:
    raise ValueError(f"{tid} not configured")
  result = entity.request(rqst, enactment_level = enactment_level)
  result.enact_hierarchy()



def enact_requests(entity=None):
  if entity is None:
    entity = config.config_root
  
  iterate_content_tree3_depth_first(entity, do_enact_requests, parent=None, strt=None)


def daemon_request(rqst, cancel, typ, ids):

  constructor_params = inspect.signature(typ).parameters

  # Filter the Namespace to include only the required arguments
  filtered_args = {k: v for k, v in ids.items() if k in constructor_params}
  entity = config.find_config(typ, **filtered_args)
  if entity is None:
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: entity not configured")
    return
  
  if cancel:
    if rqst in entity.requested:
      entity.requested[rqst].cancel(Reason.USER_REQUESTED)

      log.info(f"{make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} cancelled successfully")
    else:
      log.info(f"{make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} was not scheduled")
  else:
    if entity.request(rqst):
      config.last_request_at = datetime.now()
      entity.requested[rqst].enact_hierarchy()
    else:
      log.error(f"{make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} failed. See previous error messages.")
      return
    log.info(f"{make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} scheduled successfully")





def handle_request_command(command):
  name = command["command"]
  if not name in request_for_name:
    raise ValueError(f"unknown command {name}")
    
  rqst = request_for_name[name]
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
  daemon_request(rqst, cancel, typ, ids)



def handle_status_command(command, stream):
    
  if not "type" in command:
    raise ValueError(f"missing type for handling command: status")
 
  type_name = command["type"]
  if not type_name in type_for_command_name:
    raise ValueError(f"unknown type: {type_name}")
  typ = type_for_command_name[type_name]
  if not "identifiers" in command:
    raise ValueError(f"no identifiers given for type: {typ}")
  ids = command["identifiers"]
  if not isinstance(ids, dict):
    raise ValueError("identifiers are not a dict of type {{str:str}}")

  constructor_params = inspect.signature(typ).parameters

  # Filter the Namespace to include only the required arguments
  filtered_args = {k: v for k, v in ids.items() if k in constructor_params}
  entity = config.find_config(typ, **filtered_args)
  if entity is None:
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: entity not configured")
    return
  kdstream = KdStream(stream)
  print_status(entity, kdstream)
  kdstream.newline()


def handle_status_all_command(out):
  
  kdstream = KdStream(out)
  # log.info("starting zfs scrubs if necessary")
  print_status_many(config.config_root.content, kdstream)



def handle_clear_cache_command():

  log.info("clearing cache")
  
  remove_cache(config.cache_path)

  log.info("cache cleared")

  handle_reload_config_command()



def handle_reload_config_command():

  log.info("reloading configuration")

  init_config(config.cache_path, config.config_path)

  log.info("configuration reloaded")



def handle_scrub_all_command():
  def do(entity):
    if isinstance(entity, ZDev):
      if RequestType.SCRUB not in entity.requested:
        entity.request(RequestType.SCRUB)
  iterate_content_tree(config.config_root, do)

def handle_trim_all_command():
  def do(entity):
    if isinstance(entity, ZDev):
      if RequestType.TRIM not in entity.requested:
        entity.request(RequestType.TRIM)
  iterate_content_tree(config.config_root, do)


def cancel_requests_for_timeout():
  def do(entity):
    for rqst in entity.requested.copy():
      rqst.cancel(Reason.TIMEOUT)


  iterate_content_tree(config.config_root, do)


def handle_do_overdue_command(op: Operations):
  
  rqst: RequestType = request_for_zfs_operation[op]
  def do(entity):
    if isinstance(entity, ZDev):
      msg = f"{entity_id_string(entity)}: last {rqst.name} was {entity.last(op) or "NEVER"} (interval: {entity.effective_interval(op)})."
      if entity.is_overdue(op):
        msg += " OVERDUE."
        if rqst not in entity.requested:
          msg += f" Requesting {rqst.name}"
          log.info(msg)
          if not entity.request(rqst):
            log.error(f"{entity_id_string(entity)}: request {rqst.name} failed.")
        else:
          msg += f" {rqst.name} already requested."
          log.info(msg)
      else:
        # TODO: fix the bug that results in zmirror believing that the scrub is not yet overdue
        # while believing that the trim is overdue.
        log.info(f"{msg} Not overdue.")
  iterate_content_tree(config.config_root, do)



def handle_online_all_command(command):
  def do(entity):
    if RequestType.ONLINE not in entity.requested:
      entity.request(RequestType.ONLINE, unrequest=yes_no_absent_or_dict(command, "cancel", False, "error"))
  iterate_content_tree(config.config_root, do)


def handle_maintenance_command():
  handle_do_overdue_command(Operations.RESILVER)
  handle_do_overdue_command(Operations.TRIM)
  handle_do_overdue_command(Operations.SCRUB)


def handle_set_command(command):
  if "property" not in command:
    raise ValueError(f"no property given")
  prop = command["property"]

  if "value" not in command:
    raise ValueError(f"no value given")
  value = command["value"]

  if prop == "commands":
    config.commands_enabled = is_yes_or_true(value)
    value = to_yes(value)
  elif prop == "log-level":
    config.set_log_level(value)
  elif prop == "timeout":
    config.timeout = int(value)
  elif prop == "log-events":
    config.log_events = is_yes_or_true(value)
    value = to_yes(value)
  else:
    raise ValueError(f"unknown property: {prop}")

  log.info(f"set property {prop} to: {value}")


def handle_get_command(command, stream):
  if "property" not in command:
    raise ValueError(f"no property given")
  prop = command["property"]

  if prop == "commands":
    stream.write(to_yes(config.commands_enabled))
    value = to_yes(value)
  elif prop == "log-level":
    stream.write(config.log_level)
  elif prop == "timeout":
    stream.write(str(config.timeout))
  elif prop == "log-events":
    stream.write(to_yes(config.log_events))
  else:
    raise ValueError(f"unknown property: {prop}")




def restart_request_timer():
  log.info("restarting timeout")
  config.event_queue.put(TimerEvent.RESTART)



def handle_daemon_version_command(out):
  out.write(VERSION)
  out.write("\n")

def handle_command(command, con):
  try:
    stream = con.makefile('w')
    handler = logging.StreamHandler(stream)

    formatter = logging.Formatter('%(levelname)7s: %(message)s')
    handler.setFormatter(formatter)

    log.addHandler(handler)
    name = command["command"]
    if name == "status-all":
      handle_status_all_command(stream)
    elif name == "status":
      handle_status_command(command, stream)
    elif name == "clear-cache":
      handle_clear_cache_command()
    elif name == "reload-config":
      handle_reload_config_command()
    elif name == "scrub-all":
      handle_scrub_all_command()
    elif name == "scrub-overdue":
      handle_do_overdue_command(Operations.SCRUB)
    elif name == "trim-overdue":
      handle_do_overdue_command(Operations.TRIM)
    elif name == "resilver-overdue":
      handle_do_overdue_command(Operations.RESILVER)
    elif name == "trim-all":
      handle_trim_all_command()
    elif name == "online-all":
      handle_online_all_command(command)
    elif name == "maintenance":
      handle_maintenance_command()
    elif name == "set":
      handle_set_command(command)
    elif name == "get":
      handle_get_command(command, stream)
    elif name == "daemon-version":
      handle_daemon_version_command(stream)
    else:
      handle_request_command(command)

  except Exception as ex:
    log.error("failed to handle command")
    log.error(f"exception : {traceback.format_exc()} --- {str(ex)}")
    # scrub_parser.set_defaults(func=request_scrub_all_overdue)
  finally:
    try:
      stream.flush()
    except: #pylint: disable=bare-except
      pass
    log.removeHandler(handler)
    try:
      stream.close()
    except: #pylint: disable=bare-except
      pass
    try:
      con.close()
    except: #pylint: disable=bare-except
      pass
    log.info(f"handled user command: {name}")
  # print("client handled")



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
  "online": RequestType.ONLINE,
  "offline": RequestType.OFFLINE,
  "scrub": RequestType.SCRUB,
  "trim": RequestType.SCRUB
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


    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as con:

      try:
        # Connect the socket to the path where the server is listening
        try:
          con.connect(path)
        except Exception as ex:
          log.error(f"failed to connect to zmirror daemon ({path}): {ex}")
          return
        decoder = codecs.getincrementaldecoder('utf-8')()

        # Send data
        message = json.dumps({"ZMIRROR_COMMAND": command}).encode('utf-8')
        con.sendall(f"{len(message)}:".encode('utf-8') + message)

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


def make_send_set_property_daemon_command(property, value=None):
  def do(args):
    r = {"command": "set", "property": property}
    if value is not None:
      r["value"] = value
    else:
      r["value"] = args.value
    return r
  return make_send_daemon_wrapper(do)

def make_send_get_property_daemon_command(property, value=None):
  def do(args):
    return {"command": "get", "property": property}
  return make_send_daemon_wrapper(do)


def make_send_simple_daemon_command(command):
  def do(args):
    r = {"command": command}
    for k, v in vars(args).items():
      r[k] = v
    return r
  return make_send_daemon_wrapper(do)


def make_send_request_daemon_command(rqst, typ):
  def do(args):

    r = {
      "command": name_for_request[rqst]
    }

    if args.cancel:
      r["cancel"] = "yes"

    delattr(args, "cancel")
    r["type"] = command_name_for_type[typ]
    r["identifiers"] = vars(args)

    return r
  return make_send_daemon_wrapper(do)



def make_send_entity_daemon_command(command, typ):
  def do(args):

    return {
      "command": command,
      "type": command_name_for_type[typ],
      "identifiers": vars(args)
    }
  return make_send_daemon_wrapper(do)

