
import socket

from zmirror.entities import *
from . import config
from .config import *

from .logging import log
from .dataclasses import *
from .util import get_version, myexec, outs, copy_attrs, require_path
from . import commands as commands
from kpyutils.kiify import KdStream, is_yes_or_true, to_yes

import argparse
import sys
import logging
import inspect
import json
import codecs
import traceback
from tabulate import tabulate




def request(rqst, typ, enactment_level = sys.maxsize, **identifiers):
  tid = make_id_string(make_id(typ, **identifiers))
  entity = load_config_for_id(tid)
  if entity is None:
    raise ValueError(f"{tid} not configured")
  result = entity.request(rqst, enactment_level = enactment_level)
  result.enact_hierarchy()
  request_root.add_dependency(result)
  return result


def request_overdue(op: Operation, entity):
  result = None
  rqst: RequestType = request_for_zfs_operation[op]
  if isinstance(entity, ZDev):
    msg = f"{entity_id_string(entity)}: last {rqst.name} was {entity.last(op) or "NEVER"} (interval: {entity.effective_interval(op)})."
    overdue = entity.is_overdue(op)
    if overdue:
      if overdue.days > 356:
        msg += " OVERDUE since more than a year."
      else:
        msg += f" OVERDUE since {overdue.days} days."
      if rqst not in entity.requested:
        msg += f" Requesting {rqst.name}"
        log.info(msg)
        result = entity.request(rqst)
        if not result:
          log.error(f"{entity_id_string(entity)}: request {rqst.name} failed.")
      else:
        msg += f" {rqst.name} already requested."
        log.debug(msg)
    else:
      log.debug(f"{msg} NOT overdue.")
  return result


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

      log.info(f"executed user command `cancel {rqst.name.lower()}` for {make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} cancelled successfully")
    else:
      log.info(f"executed user command `cancel {rqst.name.lower()}` for {make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} was not scheduled, and could not be cancelled")
  else:
    if entity.request(rqst):
      config.last_request_at = datetime.now()
      entity.requested[rqst].enact_hierarchy()
    else:
      log.error(f"executed user command `{rqst.name.lower()}` for {make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} failed. See previous error messages.")
      return
    log.info(f"executed user command `{rqst.name.lower()}` for {make_id_string(make_id(typ, **filtered_args))}: request {rqst.name} scheduled successfully.")





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


def handle_list_overdue_command(command, stream):
  op = None
  if "operation" in command:
    try:
      op = Operation[str(command["operation"]).upper()]
    except Exception:
      raise ValueError(f"unknown `operation`: {command["operation"]}")
  
  result = []
  def do(entity):
    if isinstance(entity, ZDev):

      if (op and entity.is_overdue(op)) or is_anything_overdue(entity):
        result.append({
          "id" : entity_id_string(entity),
          "last_online": to_kd_date(entity.last_online),
          "last_update": to_kd_date(entity.last_update),
          "update_overdue": to_kd_date(entity.is_overdue(Operation.RESILVER)),
          "last_trim": to_kd_date(entity.last_trim),
          "trim_overdue": to_kd_date(entity.is_overdue(Operation.TRIM)),
          "last_scrub": to_kd_date(entity.last_scrub),
          "scrub_overdue": to_kd_date(entity.is_overdue(Operation.SCRUB))
        })
  iterate_content_tree(config.config_root, do)

  r = json.dumps(result)
  stream.write(r)


def to_kd_date(value):
  if isinstance(value, datetime) or isinstance(value, timedelta):
    return to_kd(value)
  else:
    return value
    


def handle_status_command(command, stream):
    
  if not "type" in command:
    raise ValueError(f"missing `type` for handling command: status")
 
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




def handle_do_overdue_command(op: Operation):
  def do(entity):
    return request_overdue(op, entity)
  iterate_content_tree(config.config_root, do)



def handle_online_all_command(command):
  def do(entity):
    if RequestType.ONLINE not in entity.requested:
      entity.request(RequestType.ONLINE, unrequest=yes_no_absent_or_dict(command, "cancel", False, "error"))
  iterate_content_tree(config.config_root, do)


def handle_maintenance_command():
  handle_do_overdue_command(Operation.RESILVER)
  handle_do_overdue_command(Operation.TRIM)
  handle_do_overdue_command(Operation.SCRUB)


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

  log.info(f"executed set command: property {prop} set to: {value}")


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






def handle_daemon_version_command(out):
  out.write(get_version())
  out.write("\n")

def handle_command(command, con):
  try:

    name = command["command"]
    
    log.info(f"handling zmirror command: {name}")

    stream = con.makefile('w')
    handler = logging.StreamHandler(stream)

    formatter = logging.Formatter('%(levelname)7s: %(message)s')
    handler.setFormatter(formatter)

    log.addHandler(handler)

    


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
      handle_do_overdue_command(Operation.SCRUB)
    elif name == "trim-overdue":
      handle_do_overdue_command(Operation.TRIM)
    elif name == "list-overdue":
      handle_list_overdue_command(command, stream)
    elif name == "resilver-overdue":
      handle_do_overdue_command(Operation.RESILVER)
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
    

    save_cache()
    enact_requests()
    commands.execute_commands()

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
    log.info(f"handled zmirror command: {name}")
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
  "trim": RequestType.TRIM
}

name_for_request = {value: key for key, value in request_for_name.items()}


def make_send_daemon_wrapper(fn, stream=sys.stdout):
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
          stream.write(decoded_data)
        remaining_data = decoder.decode(b'', final=True)
        stream.write(remaining_data)
      except KeyboardInterrupt: #pylint: disable=try-except-raise
        raise
      except Exception as ex:
        log.error(f"communication error: {ex}")
      finally:
        stream.flush()
  return do



LIST_KEYS = ["id", "last-online", "last_update", "update_overdue", "last_trim", "trim_overdue", "last_scrub", "scrub_overdue"]


def make_list_overdue_command(op: Operation):
  def do(args):
    b = StringBuilder()
    def make_command(_args):
      r = {"command": "list-overdue"}
      if op:
        r["operation"] = op.name.lower()
      return r
    
    doit = make_send_daemon_wrapper(make_command, stream=b)
    doit(args)

    items = json.loads(b.get_string())

    keys = args.keys


    for item in items:
      # print(item)
      # sys.stdout.flush()
      for k in item.copy():
        if not k in keys:
          del item[k]

    
    headers = None
    if args.format == "json":
      sys.stdout.write(json.dumps(items))
    else:
      if not args.no_headers:
        headers = {k: k for k in keys}
        table = tabulate(items, headers=headers, tablefmt=args.format)
      else:
        table = tabulate(items, tablefmt=args.format)


      sys.stdout.write(table)
    sys.stdout.flush()
  return do
  


def make_send_set_property_daemon_command(prop, value=None):
  def do(args):
    r = {"command": "set", "property": prop}
    if value is not None:
      r["value"] = value
    else:
      r["value"] = args.value
    return r
  return make_send_daemon_wrapper(do)



def make_send_get_property_daemon_command(prop, value=None):
  def do(_args):
    return {"command": "get", "property": prop}
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
    identifiers = dict()
    for fld in typ.id_fields():
      val = getattr(args, fld)
      if val is None:
        raise ValueError(f"no value given for: {fld}")
      identifiers[fld] = val
    r["identifiers"] = identifiers
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

