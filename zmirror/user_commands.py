
import socket
import shlex

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
import re
import shutil
from tabulate import tabulate

from ._version import __version__




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
    overdue_since = entity.is_overdue(op)
    if overdue_since:
      overdue = datetime.now().replace(microsecond=0) - overdue_since
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


def daemon_request(rqst: RequestType, cancel: bool, typ, ids):

  constructor_params = inspect.signature(typ).parameters

  # Filter the Namespace to include only the required arguments
  filtered_args = {k: v for k, v in ids.items() if k in constructor_params}
  entity = config.find_config(typ, **filtered_args)
  if entity is None:
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: entity not configured")
    return
  do_request(entity, rqst, cancel)

  
def do_request(entity, rqst: RequestType, cancel: bool):
  if cancel:
    if rqst in entity.requested:
      entity.requested[rqst].cancel(Reason.USER_REQUESTED)
      log.info(f"executed user command `cancel {rqst.name.lower()}` for {entity_id_string(entity)}: request {rqst.name} cancelled successfully")
    else:
      log.info(f"executed user command `cancel {rqst.name.lower()}` for {entity_id_string(entity)}: request {rqst.name} was not scheduled, and could not be cancelled")
  else:
    if entity.request(rqst):
      config.last_request_at = datetime.now()
      log.info(f"executed user command `{rqst.name.lower()}` for {entity_id_string(entity)}: request {rqst.name} scheduled successfully.")
    else:
      log.error(f"executed user command `{rqst.name.lower()}` for {entity_id_string(entity)}: request {rqst.name} failed. See previous error messages.")
      return





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
  if type_name == "all":
    handle_all_request(rqst)
  elif type_name == "group":
    if "group" not in command:
      raise ValueError(f"missing group for handling group command: {command}")
    handle_group_request(rqst, command["group"], cancel=cancel)

  elif type_name in TYPE_FOR_NAME:
    typ = TYPE_FOR_NAME[type_name]

    if not "identifiers" in command:
      raise ValueError(f"no identifiers given for type: {typ}")
    ids = command["identifiers"]
    if not isinstance(ids, dict):
      raise ValueError("identifiers are not a dict of type {{str:str}}")
    daemon_request(rqst, cancel, typ, ids)  
  else:
    raise ValueError(f"unknown type: {type_name}")
  
  


def handle_group_request(rqst: RequestType, group: str, cancel: bool = False):
  log.info(f"handling group request for group: {group}")
  def do(entity):
    if hasattr(entity, "groups"):
      if entity.groups and group in entity.groups:
        do_request(entity, rqst, cancel= cancel)
  iterate_content_tree(config.config_root, do)



def handle_all_request(rqst: RequestType, cancel: bool = False):
  def do(entity):
    # TODO figure out if enact_... is the best way to figure out if entity can do this
    # attr = f"enact_{rqst.name.lower()}"
    # if hasattr(entity, attr):
    if hasattr(entity, "request"):
      do_request(entity, rqst, cancel= cancel)
  iterate_content_tree(config.config_root, do)

    


def handle_status_command(command, stream):
    
  if not "type" in command:
    raise ValueError(f"missing `type` for handling command: status")
 
  type_name = command["type"]
  if type_name == "all":
    handle_status_all_command(stream)
  elif type_name == "group":
    
    if "group" not in command:
      raise ValueError(f"missing group for handling group command: {command}")
    handle_status_group_command(command["group"], stream)
  else:
    if not type_name in TYPE_FOR_NAME:
      raise ValueError(f"unknown type: {type_name}")
    typ = TYPE_FOR_NAME[type_name]
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



def handle_status_group_command(group: str, out):
  lst = []
  def do(entity):
    if hasattr(entity, "groups") and group in entity.groups:
      lst.append(entity)
  iterate_content_tree(config.config_root, do)
  kdstream = KdStream(out)
  print_status_many(lst, kdstream)

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


def handle_shutdown_command():

  config.event_queue.put(None)
  log.info("shutdown requested")


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
  elif prop == "event-handlers":
    config.event_handlers_enabled = is_yes_or_true(value)
    value = to_yes(value)
  elif prop == "log-level":
    config.set_log_level(value)
  elif prop == "timeout":
    config.timeout = int(value)
  elif prop == "log-events":
    enabled = is_yes_or_true(value)
    if enabled:
      config.log_events = True
      config.log_full_events = False
    else:
      config.log_events = False
      config.log_full_events = False
    value = to_yes(value)
  elif prop == "log-full-events":
    enabled = is_yes_or_true(value)
    if enabled:
      config.log_events = False
      config.log_full_events = True
    else:
      config.log_events = False
      config.log_full_events = False
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
  elif prop == "log-level":
    stream.write(config.log_level)
  elif prop == "timeout":
    stream.write(str(config.timeout))
  elif prop == "log-events":
    stream.write(to_yes(config.log_events))
  elif prop == "log-full-events":
    stream.write(to_yes(config.log_full_events))
  else:
    raise ValueError(f"unknown property: {prop}")






def handle_daemon_version_command(out):
  out.write(__version__)
  out.write("\n")

def handle_command(command, con):
  try:

    name = command["command"]
    
    log.debug(f"handling zmirror command: {name}")

    stream = con.makefile('w')
    handler = logging.StreamHandler(stream)

    formatter = logging.Formatter('%(levelname)7s: %(message)s')
    handler.setFormatter(formatter)

    log.addHandler(handler)

    
    commit = True

    if name == "status-all":
      handle_status_all_command(stream)
      commit = False
    elif name == "status":
      
      handle_status_command(command, stream)
      commit = False
    elif name == "list":
      handle_list_command(command, stream)
      commit = False
    elif name == "get":
      handle_get_command(command, stream)
      commit = False
    elif name == "daemon-version":
      handle_daemon_version_command(stream)
      commit = False
    elif name == "shutdown":
      handle_shutdown_command()
      commit = False
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
    else:
      handle_request_command(command)
    
    return commit

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
    log.debug(f"handled zmirror command: {name}")
  # print("client handled")



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
          raise
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
        raise
      finally:
        stream.flush()
  return do



LIST_DEFAULT_KEYS = ["hrid", "state", "last_online", "last_update", "update_overdue", "last_trim", "trim_overdue", "last_scrub", "scrub_overdue", "errors", "operations"]
LIST_KEYS = ["id", "hrid", "state", "parent", "depth", "last_online", "last_update", "update_overdue", "last_trim", "trim_overdue", "last_scrub", "scrub_overdue", "errors", "operations"]


def make_list_command(op: Operation, overdue=False):
  def do(args):
    b = StringBuilder()
    def make_command(_args):
      # only zdev is supported for now
      r = {"command": "list"}
      if op:
        r["operation"] = op.name.lower()
      if overdue:
        r["overdue"] = True
      if args.types:
        r["types"] = args.types
      if args.sort:
        r["sort"] = args.sort
      if args.groups:
        r["groups"] = args.groups
      if args.ids:
        r["ids"] = args.ids
      if args.id_regex is not None:
        r["id_regex"] = args.id_regex
      if args.hierarchy:
        r["hierarchy"] = True
      if args.graph:
        r["graph"] = True
      
      return r
    
    doit = make_send_daemon_wrapper(make_command, stream=b)
    doit(args)

    try:
      result = json.loads(b.get_string())
    except BaseException:
      log.error("an error occurred on the server: %s", b.get_string())
      return

    keys = list(args.keys)
    if args.extra_columns:
      for col in args.extra_columns:
        if col not in keys:
          keys.append(col)

    items = result
    for item in items:
      # print(item)
      # sys.stdout.flush()
      for k in item.copy():
        if k == "depth":
          continue
        if not k in keys:
          del item[k]

    
    headers = None
    user_selected_format = hasattr(args, "format")
    table_format = args.format if user_selected_format else "simple"
    terminal_size = shutil.get_terminal_size(fallback=(120, 24))

    if table_format == "json":
      for item in items:
        if "depth" in item and "depth" not in keys:
          del item["depth"]
      sys.stdout.write(json.dumps(items))
    else:
      for item in items:
        item_indent_depth = int(item.get("depth", 0) or 0)
        for key in keys:
          if key not in item:
            item[key] = ""
            continue

          val = item[key]
          if val is None:
            val = "-"
          elif isinstance(val, bool):
            if val:
              val = f"{to_kd(val)}"
            else:
              val = "-"
          elif isinstance(val, list):
            if len(val) == 0:
              val = "-"
            else:
              val = ', '.join(val)
          elif isinstance(val, dict):
            val = special_ki_from_json(val)
            if hasattr(val, "__kiify__"):
              val = f"{to_kd(val)}"
          if item_indent_depth > 0 and len(keys) > 0 and key == keys[0]:
            val = f"{'\u2800\u2800' * item_indent_depth}{val}"
          item[key] = val

        if "depth" in item and "depth" not in keys:
          del item["depth"]
          

      tabulate_kwargs = {}
      if not user_selected_format:
        terminal_columns = terminal_size.columns
        if terminal_columns < 220:
          tabulate_kwargs["maxheadercolwidths"] = 7
        else:
          key_labels = [str(key) for key in keys]

          wide_key = "id" if "id" in keys else ("hrid" if "hrid" in keys else None)
          if len(key_labels) > 1 and wide_key is not None:
            non_id_count = len(key_labels) - 1
            non_id_headers = [label for label in key_labels if label != wide_key]

            observed_id_width = max([len(str(item.get(wide_key, ""))) for item in items], default=32)
            max_id_budget = max(int(terminal_columns * 0.65), 12)
            id_budget = min(max(observed_id_width, 24), max_id_budget)

            separator_budget = max(len(key_labels) - 1, 0) * 3
            remaining_for_non_id = max(terminal_columns - id_budget - separator_budget, 1)
            non_id_header_width = max(8, remaining_for_non_id // non_id_count)

            if sum([len(label) for label in non_id_headers]) > remaining_for_non_id:
              tabulate_kwargs["maxheadercolwidths"] = [
                len(label) if label == wide_key or len(label) <= non_id_header_width else non_id_header_width
                for label in key_labels
              ]
          else:
            separator_budget = max(len(key_labels) - 1, 0) * 3
            usable_columns = max(terminal_columns - separator_budget, 1)
            per_column_width = max(8, usable_columns // max(len(key_labels), 1))
            if max([len(label) for label in key_labels], default=0) > per_column_width:
              tabulate_kwargs["maxheadercolwidths"] = per_column_width

      table_rows = [[item.get(key, "") for key in keys] for item in items]

      if not args.no_headers:
        if user_selected_format or terminal_size.columns >= 220:
          headers = [str(k) for k in keys]
        else:
          headers = [str(k).replace("_", "\n") for k in keys]
        table = tabulate(table_rows, headers=headers, tablefmt=table_format, **tabulate_kwargs)
      else:
        table = tabulate(table_rows, tablefmt=table_format, **tabulate_kwargs)


      sys.stdout.write(table)
    sys.stdout.flush()
  return do



def get_entity_depth(entity: Entity):
  depth = 0
  current = getattr(entity, "parent", None)
  while current is not None:
    depth += 1
    current = getattr(current, "parent", None)
  return max(depth - 1, 0)


def entity_to_table_entry(entity: Entity, tree=False, indent_depth=None, repeated=False):
  cache = cached(entity)
  added = None
  parent = getattr(entity, "parent", None)
  parent_id = None
  if parent is not None and not isinstance(parent, ZMirror):
    parent_id = entity_id_string(parent)
  if cache.added is not None:
    added = datetime.fromtimestamp(cache.added)
  id_value = entity_id_string(entity)
  hrid_value = entity.hrid()
  row_indent_depth = 0
  if repeated:
    hrid_value = f"({hrid_value})"

  if indent_depth is not None:
    row_indent_depth = indent_depth
  elif tree:
    row_indent_depth = get_entity_depth(entity)

  id_value = entity_id_string(entity)

  if repeated:
    return {
      "id": id_value,
      "hrid": hrid_value,
      "state": cache.state.what.name.lower() if cache.state is not None and cache.state.what is not None else "-",
      "parent": parent_id,
      "depth": row_indent_depth
    }

  if isinstance(entity, ZDev):
    return {
        "id" : id_value,
        "hrid": hrid_value,
        "state": cache.state.what.name.lower() if cache.state is not None and cache.state.what is not None else "-",
        "parent": parent_id,
        "depth": row_indent_depth,
        "last_online": special_ki_to_json(to_kd_date(entity.get_last_online())),
        "added": special_ki_to_json(to_kd_date(added)),
        "last_update": special_ki_to_json(to_kd_date(entity.get_last_update())),
        "update_overdue": to_kd_date(entity.is_overdue(Operation.RESILVER)),
        "last_trim": to_kd_date(cache.last_trim),
        "trim_overdue": to_kd_date(entity.is_overdue(Operation.TRIM)),
        "last_scrub": to_kd_date(cache.last_scrub),
        "scrub_overdue": to_kd_date(entity.is_overdue(Operation.SCRUB)),
        "errors": cache.errors,
        "operations": [get_name_for_operaiton(op.what) for op in cache.operations]
      }
  else:
    return {
        "id" : id_value,
        "hrid": hrid_value,
        "state": cache.state.what.name.lower() if cache.state is not None and cache.state.what is not None else "-",
        "parent": parent_id,
        "depth": row_indent_depth,
        "last_online": special_ki_to_json(to_kd_date(entity.get_last_online())),
        "added": special_ki_to_json(to_kd_date(added))
      }

def handle_list_command(command, stream):
  op = None
  overdue = False
  if "overdue" in command:
    overdue = True
    if "operation" in command:
      try:
        op = Operation[str(command["operation"]).upper()]
      except Exception:
        raise ValueError(f"unknown `operation`: {command["operation"]}")
  groups = None
  if "groups" in command:
    groups = command["groups"]
    if not isinstance(groups, list):
      raise ValueError("`groups` must be a list")
  

  types = None
  if "types" in command:
    types =  [get_type_for_name(tp) for tp in command["types"]]

  ids = None
  if "ids" in command:
    ids = command["ids"]
    if not isinstance(ids, list):
      raise ValueError("`ids` must be a list")
    ids = set(ids)

  id_regex = None
  if "id_regex" in command:
    id_regex = command["id_regex"]
    if not isinstance(id_regex, str):
      raise ValueError("`id_regex` must be a string")
    try:
      id_regex = re.compile(id_regex)
    except re.error as ex:
      raise ValueError(f"invalid `id_regex`: {ex}") from ex

  hierarchy = False
  if "hierarchy" in command:
    hierarchy = command["hierarchy"]
    if not isinstance(hierarchy, bool):
      raise ValueError("`hierarchy` must be a bool")

  graph = False
  if "graph" in command:
    graph = command["graph"]
    if not isinstance(graph, bool):
      raise ValueError("`graph` must be a bool")

  sort_attr = None
  if "sort" in command:
    sort_attr = command["sort"]


  def matches_group_type_or_id(entity):
    if groups is not None:
      if not hasattr(entity, "groups"):
        return False
      group_found = False
      for group in groups:
        if group in entity.groups:
          group_found = True
          break
      if not group_found:
        return False

    if types is not None:
      type_found = False
      for entity_type in types:
        if isinstance(entity, entity_type):
          type_found = True
          break
      if not type_found:
        return False

    if ids is not None:
      if not entity_id_string(entity) in ids:
        return False

    if id_regex is not None:
      if not id_regex.search(entity_id_string(entity)):
        return False

    return True


  def matches_overdue(entity):
    if not overdue:
      return True

    if not hasattr(entity, "is_overdue"):
      return False

    if op:
      return bool(entity.is_overdue(op))
    return is_anything_overdue(entity)


  entities_in_config_order = []

  def collect_entities(entity):
    if isinstance(entity, ZMirror):
      return
    entities_in_config_order.append(entity)

  iterate_content_tree(config.config_root, collect_entities)

  seed_entities = []
  for entity in entities_in_config_order:
    if matches_group_type_or_id(entity) and matches_overdue(entity):
      seed_entities.append(entity)


  included_entities_by_ref = {}

  def include_entity(entity):
    included_entities_by_ref[id(entity)] = entity

  for entity in seed_entities:
    include_entity(entity)

  if hierarchy:
    mode_down = "down"
    mode_up_only = "up_only"

    def hierarchy_neighbors(entity, mode, is_root):
      neighbors = []

      def add(neighbor, next_mode):
        if neighbor is None or isinstance(neighbor, ZMirror):
          return
        neighbors.append((neighbor, next_mode))

      if mode == mode_up_only:
        add(getattr(entity, "parent", None), mode_up_only)
      else:
        if isinstance(entity, ZPool) and not is_root:
          return []

        content = getattr(entity, "content", None)
        if isinstance(content, list):
          for child in content:
            add(child, mode_down)

        parent = getattr(entity, "parent", None)
        if parent is not None and not isinstance(parent, ZMirror):
          add(parent, mode_up_only)

        if isinstance(entity, ZDev):
          pool = config.find_config(ZPool, name=entity.pool)
          add(pool, mode_down)
        elif isinstance(entity, ZPool) and is_root:
          if entity.name in config.zfs_blockdevs:
            for zdev in config.zfs_blockdevs[entity.name].values():
              add(zdev, mode_down)

      dedup = []
      refs = set()
      for neighbor, next_mode in neighbors:
        key = (id(neighbor), next_mode)
        if not key in refs:
          refs.add(key)
          dedup.append((neighbor, next_mode))

      return dedup

    for root in seed_entities:
      root_ref = id(root)
      stack = [(root, mode_down)]
      visited = set()
      while stack:
        current, mode = stack.pop()
        cref = id(current)
        if cref in visited:
          continue

        visited.add(cref)
        include_entity(current)

        for neighbor, next_mode in hierarchy_neighbors(current, mode, cref == root_ref):
          if id(neighbor) not in visited:
            stack.append((neighbor, next_mode))


  def sorted_siblings(entities):
    if sort_attr is None:
      return entities
    return sorted(entities, key=sort_key_for_entity)


  ordered_entities = []
  ordered_entities_with_depth = []

  def sort_entities(entities):
    if sort_attr is None:
      return entities
    return sorted(entities, key=sort_key_for_entity)

  def sort_key_for_entity(entity):
    value = entity_to_table_entry(entity).get(sort_attr, "")
    if value is None:
      return "-"
    if isinstance(value, list):
      if len(value) == 0:
        return "-"
      return ', '.join(value)
    if isinstance(value, dict):
      value = special_ki_from_json(value)
      if hasattr(value, "__kiify__"):
        return f"{to_kd(value)}"
      return str(value)
    return value

  if graph:
    roots = list(seed_entities)
    roots = sort_entities(roots)

    mode_down = "down"
    mode_up_only = "up_only"

    def graph_children(entity, mode, is_root):
      children = []

      def add(child, next_mode):
        if child is None or isinstance(child, ZMirror):
          return
        children.append((child, next_mode))

      if mode == mode_up_only:
        add(getattr(entity, "parent", None), mode_up_only)
      else:
        if isinstance(entity, ZPool) and not is_root:
          return []

        content = getattr(entity, "content", None)
        if isinstance(content, list):
          for child in content:
            add(child, mode_down)

        parent = getattr(entity, "parent", None)
        if parent is not None and not isinstance(parent, ZMirror):
          add(parent, mode_up_only)

        if isinstance(entity, ZDev):
          pool = config.find_config(ZPool, name=entity.pool)
          add(pool, mode_down)
        elif isinstance(entity, ZPool) and is_root:
          if entity.name in config.zfs_blockdevs:
            for zdev in config.zfs_blockdevs[entity.name].values():
              add(zdev, mode_down)

      dedup = []
      refs = set()
      for child, next_mode in children:
        cref = id(child)
        key = (cref, next_mode)
        if not key in refs:
          refs.add(key)
          dedup.append((child, next_mode))

      if sort_attr is None:
        return dedup

      return sorted(dedup, key=lambda pair: sort_key_for_entity(pair[0]))

    def graph_walk(entity, depth, visited, mode, root_ref, prev_ref=None):
      ref = id(entity)
      ordered_entities_with_depth.append((entity, depth))

      if ref in visited:
        return
      visited.add(ref)

      for child, next_mode in graph_children(entity, mode, ref == root_ref):
        if id(child) == prev_ref:
          continue
        graph_walk(child, depth + 1, visited, next_mode, root_ref, ref)

    for root in roots:
      graph_walk(root, 0, set(), mode_down, id(root), None)

  elif hierarchy:
    def walk(entity):
      if not isinstance(entity, ZMirror):
        if id(entity) in included_entities_by_ref:
          ordered_entities.append(entity)

      content = getattr(entity, "content", None)
      if isinstance(content, list):
        children = sorted_siblings(list(content))
        for child in children:
          walk(child)

    walk(config.config_root)
  else:
    for entity in entities_in_config_order:
      if id(entity) in included_entities_by_ref:
        ordered_entities.append(entity)

    if sort_attr is not None:
      ordered_entities = sorted(ordered_entities, key=sort_key_for_entity)

  if graph:
    result = [entity_to_table_entry(entity, indent_depth=depth) for entity, depth in ordered_entities_with_depth]
  else:
    result = [entity_to_table_entry(entity, tree=hierarchy) for entity in ordered_entities]

  r = json.dumps(result)
  stream.write(r)



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

def make_send_all_daemon_command(cmd: str):
  def do(args):
    r = {
      "command": cmd,
      "type": "all"
    }
    if hasattr(args, "cancel") and args.cancel:
      r["cancel"] = "yes"
    return r
  return make_send_daemon_wrapper(do)

def make_send_group_daemon_command(cmd: str):
  def do(args):
    r = {
      "command": cmd,
      "type": "group",
      "group": args.group
    }
    if hasattr(args, "cancel") and args.cancel:
      r["cancel"] = "yes"
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
    r["type"] = NAME_FOR_TYPE[typ]
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
      "type": NAME_FOR_TYPE[typ],
      "identifiers": vars(args)
    }
  return make_send_daemon_wrapper(do)
def run_and_print_command(command: str, stream):
  stream.write(f"$ {command}\n")
  returncode, _output, response, errors = myexec(command)

  wrote_output = False
  for line in response:
    stream.write(f"stdout: {line}\n")
    wrote_output = True
  for line in errors:
    stream.write(f"stderr: {line}\n")
    wrote_output = True
  if not wrote_output:
    stream.write("(no output)\n")

  stream.write(f"exit code: {returncode}\n")
  stream.write("\n")
  return returncode, response, errors


def handle_check_trim_command(args):
  stream = getattr(args, "stream", sys.stdout)

  device = args.device.strip()
  if not device.startswith("/dev/"):
    device = f"/dev/{device}"

  stream.write(f"checking trim capability for: {device}\n\n")

  mode = None
  provisioning_mode_path = config.find_provisioning_mode(device)
  if provisioning_mode_path is None:
    stream.write(
      "provisioning_mode path was not found; kernel-side recognition check skipped.\n\n"
    )
  else:
    quoted_path = shlex.quote(provisioning_mode_path)
    _returncode, response, _errors = run_and_print_command(
      f"cat {quoted_path}",
      stream,
    )
    if response:
      mode = response[-1].strip().lower()

  quoted_device = shlex.quote(device)
  returncode, response, _errors = run_and_print_command(
    f"sg_vpd -a {quoted_device} | grep -i map",
    stream,
  )

  unmap_hint = None
  reports_support = False
  if returncode != 0:
    interpretation = "interpretation: could not evaluate TRIM/UNMAP support from command output."
  else:
    for line in response:
      lower = line.lower()
      if "maximum unmap lba count" in lower:
        unmap_hint = line.strip()
      if "unmap command not implemented" in lower:
        reports_support = False
      elif "maximum unmap lba count:" in lower and "not implemented" not in lower:
        reports_support = True

    if reports_support and mode == "full":
      hint = unmap_hint or "Maximum unmap LBA count reported"
      interpretation = f"interpretation: device reports TRIM/UNMAP support ({hint}) but kernel did not recognize it (mode is `full` instead of `unmap`)."
    elif reports_support and mode == "unmap":
      hint = unmap_hint or "Maximum unmap LBA count reported"
      interpretation = f"interpretation: device reports TRIM/UNMAP support ({hint}) and kernel also reports `unmap`."
    elif reports_support:
      hint = unmap_hint or "Maximum unmap LBA count reported"
      if mode is None:
        interpretation = f"interpretation: device reports TRIM/UNMAP support ({hint}), but kernel mode could not be determined."
      else:
        interpretation = f"interpretation: device reports TRIM/UNMAP support ({hint}), kernel mode is `{mode}`."
    else:
      interpretation = "interpretation: device does not report TRIM/UNMAP support in SCSI VPD output."

  stream.write(f"{interpretation}\n")
  stream.write("WARNING: this interpretation is preliminary; zmirror provides no guarantees, especially no guarantee that TRIM support is reported correctly for this device.\n")


def handle_enable_trim_command(args):
  stream = getattr(args, "stream", sys.stdout)

  device = args.device.strip()
  if not device.startswith("/dev/"):
    device = f"/dev/{device}"

  stream.write(f"manually enabling trim for: {device}\n\n")

  provisioning_mode_path = config.find_provisioning_mode(device)
  if provisioning_mode_path is None:
    stream.write("provisioning_mode path was not found; cannot enable trim for this device.\n")
    return

  quoted_path = shlex.quote(provisioning_mode_path)
  returncode, response, _errors = run_and_print_command(f"cat {quoted_path}", stream)
  if returncode != 0 or not response:
    stream.write("could not determine current provisioning_mode; no changes applied.\n")
    return

  current_mode = response[-1].strip().lower()
  if current_mode == "unmap":
    stream.write("trim already enabled (`unmap`); no changes applied.\n")
    return

  run_and_print_command(f"echo unmap > {quoted_path}", stream)
  _verify_returncode, verify_response, _verify_errors = run_and_print_command(
    f"cat {quoted_path}",
    stream,
  )

  if verify_response and verify_response[-1].strip().lower() == "unmap":
    stream.write("trim enable command applied; provisioning_mode now reports `unmap`.\n")
  else:
    stream.write("trim enable command was attempted, but provisioning_mode still does not report `unmap`.\n")
