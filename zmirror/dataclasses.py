#!/bin/python


#pylint: disable=unsubscriptable-object
#pylint: disable=not-an-iterable
#pylint: disable=invalid-field-call
#pylint: disable=no-member
#pylint: disable=unsupported-membership-test
#pylint: disable=useless-parent-delegation
#pylint: disable=no-else-return
#pylint: disable=abstract-method
#pylint: disable=wildcard-import


from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any
import time
from .util import read_file
from enum import Enum
import shutil
from promise import Promise


from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream, yes_no_absent_or_dict, KiSymbol
from kpyutils.escaping import backslash_escape
from kpyutils.promises import fulfilled_promise


from .logging import log
from . import commands as commands
from . import config as config
from .config import iterate_content_tree3_depth_first
from .requests import *
import dateparser
import re

def human_readable_id(entity):
  if not entity:
    raise ValueError("entity cannot be None")
  r = entity_id_string(entity)
  if hasattr(entity, "info"):
    entity = uncached(cached(entity))
    if entity:
      v = entity.info
      if v is not None:
        return f"{r} ({v})"
    else:
      return f"{r} (unconfigured)"
  return r

config.human_readable_id = human_readable_id

def do_enact_requests(entity, *_args, **_kwargs):
  if isinstance(entity, Entity):
    entity.enact_requests()

class When:
  what: object
  when: datetime

  def __init__(self, what, when=None):
    self.when = when
    self.what = what

  def __kiify__(self, kd_stream: KdStream):
    if self.when is not None:
      kd_stream.stream.print_raw(self.__class__.__name__)
      kd_stream.stream.print_raw(" ")
      kd_stream.print_obj(self.when)
      kd_stream.stream.indent()
      kd_stream.stream.newline()
      kd_stream.print_obj(self.what)
      kd_stream.stream.dedent()
    else:
      kd_stream.print_obj(self.what)



@yaml_data
class Since(When):
  def __init__(self, what, when=None):
    super().__init__(what, when)


def since_in(x, lst):
  return any(since.what == x for since in lst)

def since_remove(x, lst):
  lst[:] = [e for e in lst if e.what != x]

def since_insert_if_not_in(x: Since, lst):
  if not since_in(x.what, lst):
    lst.append(x)

@yaml_enum
class EntityState(KiEnum):
  # unknown state
  UNKNOWN = 99

  # offline and not present (inactive)
  DISCONNECTED = 0

  # present and online (active)
  CONNECTED = 1

  # ACTIVE means: CONNECTED, and children/dependents are wired/usable.
  # IMPORTANT: this numeric value MUST NOT collide with RequestType values.
  # state_corresponds_to_request(...) falls back to `state.value == request.value`
  # for request types without explicit mapping, so collisions would create false
  # request/state matches. 100 is chosen to stay away from RequestType numbers.
  ACTIVE = 100

  # present and offline (inactive)
  INACTIVE = 2


def state_corresponds_to_request(state, request):
  if request == RequestType.APPEAR:
    return is_present_or_online_state(state)
  if request == RequestType.OFFLINE:
    return is_offline_state(state)
  if request == RequestType.ONLINE:
    return is_online_state(state)
  # Fallback relies on aligned enum values for request/state pairs that are not
  # explicitly mapped above (for example SNAPSHOT). Keep state/request numeric
  # values intentionally non-colliding except for intended pairs.
  return state.value == request.value

def operation_corresponds_to_request(oper, request):
  return oper.value == request.value




@yaml_enum
class Operation(KiEnum):
  RESILVER = 1
  SCRUB = 2
  TRIM = 3


def enum_command_name(enum):
  return enum.name.lower()


def is_online_state(state):
  return state in {EntityState.CONNECTED, EntityState.ACTIVE}


def is_online(entity):
  state = entity.get_state()
  return is_online_state(state)


def is_offline_state(state):
  return state in {EntityState.INACTIVE, EntityState.DISCONNECTED}



def is_present_or_online_state(state):
  return state in {EntityState.INACTIVE, EntityState.ACTIVE} or is_online_state(state)


def is_present_or_online(entity):
  state = entity.get_state()
  return is_present_or_online_state(state)



name_for_operation = {
  Operation.RESILVER: "update",
  Operation.SCRUB: enum_command_name(Operation.SCRUB),
  Operation.TRIM: enum_command_name(Operation.TRIM)
}

def get_last_property_name_for_operation(op: Operation):
  return f"last_{name_for_operation[op]}"

def get_name_for_operaiton(op: Operation):
  return name_for_operation[op]

request_for_zfs_operation = {
  Operation.RESILVER: RequestType.ONLINE,
  Operation.SCRUB: RequestType.SCRUB,
  Operation.TRIM: RequestType.TRIM
}

zfs_operation_for_request = {value: key for key, value in request_for_zfs_operation.items()}


@yaml_data("zmirror", also_use_class_name=False)
class ZMirror:
  log_events: bool = False
  log_full_events: bool = False
  enable_commands: bool = True
  enable_event_handlers: bool = True
  ssd: bool = True
  timeout: int = 300
  log_level: str = "info"



  content: list = field(default_factory=list)
  notes: str = None


  update_interval: str = None
  available_update_interval: str = None
  scrub_interval: str = None
  trim_interval: str = None
  zpool_import_args: str = None
  update_scheduler: list = field(default_factory=list)
  maintenance_scheduler: list = field(default_factory=list)
  regular_status_scheduler: list = field(default_factory=lambda: [{"times": ["00:00", "10:00", "20:00", "30:00", "40:00", "50:00"]}])

  def id(self):
    return make_id(self)
  
  @classmethod
  def id_fields(cls):
    return []



def cached(entity):
  if entity.is_cache:
    return entity
  tp, kwargs = entity.id()
  cache = config.find_or_create_cache(tp, **kwargs)
  return cache



def make_id(o, **kwargs):
  if not isinstance(o, type):
    o = type(o)
  return (o, kwargs)


def get_name_for_type(tp):
  return NAME_FOR_TYPE[tp]
  # if tp in NAME_FOR_TYPE:
  #  return NAME_FOR_TYPE[tp]
  # return re.sub(r'(?<=\w)[A-Z]', lambda x: '-' + x.group().lower(), tp.__name__).lower()



def get_type_for_name(nm):
  if not nm in TYPE_FOR_NAME:
    raise ValueError(f"unknown type: {nm}")
  return TYPE_FOR_NAME[nm]



def make_id_string(x, **kwargs):
  if isinstance(x, tuple):
    return make_id_string(x[0], **x[1])
  elif not isinstance(x, type):
    raise ValueError("value must be type or tuple of type and arguments")
  return get_name_for_type(x) + "|" + '|'.join(f"{key}:{kwargs[key]}" for key in x.id_fields())

def entity_id_string(o):
  return make_id_string(o.id())



@yaml_data
class Onlineable:

  def unsupported_request(self, request_type):
    if request_type in {RequestType.ONLINE, RequestType.OFFLINE}:
      return None
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  

  # these event handlers will be called on all zpools only when `zmirror startup` is called
  on_startup: list = field(default_factory=list, kw_only=True)





class DependentNotFound(Exception):
  """Exception raised when a dependent is not found."""




def state_since_factory():
  return Since(EntityState.UNKNOWN, None)


def unix_timestamp_now():
  return int(time.time())

@yaml_data
class Entity:

  parent = None
  cache = None
  is_cache: bool = False
  requested: dict = field(default_factory=dict)
  state: Since = field(default_factory=state_since_factory, metadata={"db": True})
  added: int = field(default_factory=unix_timestamp_now, metadata={"db": True})
  last_online: datetime = field(metadata={"db": True}, default=None)
  notes: str = None
  groups: list = field(default_factory=list)


  # these are the fields we want serialized on change
  def __getstate__(self):
    r = {}
    for i in type(self).id_fields():
      r[i] = getattr(self, i)
    for n, f in type(self).__dataclass_fields__.items():
      if f.metadata and "db" in f.metadata and f.metadata["db"] == True:
        r[n] = getattr(self, n)
    return r



  @classmethod
  def id_fields(cls):
    raise NotImplementedError()

  def hrid(self):
    type_name = get_name_for_type(type(self))
    id_fields = type(self).id_fields()
    if len(id_fields) == 0:
      return f"{type_name}:"

    main_field = id_fields[-1]
    main_value = getattr(self, main_field, None)
    if main_value is None:
      main_value = "-"

    if len(id_fields) == 1:
      return f"{type_name}: {main_value}"

    rest_values = []
    for field_name in id_fields[:-1]:
      field_value = getattr(self, field_name, None)
      if field_value is None:
        field_value = "-"
      rest_values.append(f"{field_value}")

    return f"{type_name}: {main_value} ({', '.join(rest_values)})"


  def get_last_online(self):
    cache = cached(self)
    now = inaccurate_now()
    if is_online_state(cache.state.what):
      cache.last_online = now
      return KiSymbol("now")
    return cache.last_online
  


  def remove_request(self, request_type):
    return self.requested.remove(request_type)


  def enact_requests(self):
    copy = self.requested.copy()
    for request_type in copy:
      request = copy[request_type]
      request.enact_hierarchy()

  def state_allows(self, request_type):
    state = cached(self).state.what
    if is_online_state(state) and request_type == RequestType.OFFLINE:
      return True
    elif state == EntityState.INACTIVE and request_type == RequestType.ONLINE:
      return True
    return False
  
  def unsupported_request(self, _request_type):
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  

  def is_fulfilled(self, request: Request):
    state = cached(self).state.what
    r = state_corresponds_to_request(state, request.request_type)
    return r

  def enact_cancel(self, request_type):

    attr = f"enact_cancel_{request_type.name.lower()}"
    if hasattr(self, attr):
      def on_fail(rslt):
        if isinstance(rslt, tuple) and len(rslt) == 4:
          cmd, _, _, errors = rslt
          log.error(f"command `{cmd.command}` failed: \n\t{"\n\t".join(errors)}")
        else:
          log.error(f"command `{cmd.command}` failed: {rslt}")

      enact = getattr(self, attr)
      promise = enact()
      promise.catch(on_fail)
    else:
      log.debug(f"{human_readable_id(self)}: request type cannot be cancelled by this entity: {request_type}")

  def enact(self, request):

    request_type = request.request_type

    attr = f"enact_{request_type.name.lower()}"
    if hasattr(self, attr):
      def on_fail(rslt):
        request.fail(Reason.COMMAND_FAILED)
        if isinstance(rslt, tuple) and len(rslt) == 4:
          cmd, _, _, errors = rslt
          log.error(f"command `{cmd.command}` failed: \n\t{"\n\t".join(errors)}")
        else:
          log.error(f"command `{cmd.command}` failed: {rslt}")

      enact = getattr(self, attr)
      promise = enact()
      promise.catch(on_fail)
      request.set_enacted()
    else:
      log.debug(f"{human_readable_id(self)}: request type cannot be enacted by this entity: {request_type}")


  def print_status(self, kdstream):
    for prop in type(self).id_fields():
      kdstream.print_property(self, prop)
    kdstream.newline()

    cache = cached(self)
    kdstream.print_property(cache, "state")

    if self.requested:
      kdstream.newline()
      kdstream.print_property(self, "requested")


    if not is_online_state(cache.state.what):
      kdstream.newline()
      kdstream.print_property(cache, "last_online", nil=KiSymbol("never"))

  def handle_onlined(self, state=EntityState.CONNECTED):
    prev_state = self.set_state(state, "onlined")
    succeed_request(self, RequestType.ONLINE)
    if prev_state is None:
      return
    tell_parent_child_online(self.parent, self, prev_state)


  def request_dependencies(self, request_type: RequestType, enactment_level = sys.maxsize):
    if request_type in {RequestType.ONLINE, RequestType.APPEAR}:
      if hasattr(self.parent, "request"):
        return [self.parent.request(RequestType.ONLINE, enactment_level - 1)]
      return []
    else:
      raise ValueError(f"{human_readable_id(self)}: bug: @Entity.request_dependencies:  {request_type} not implemented")

  def prepare_request(self, request_type: RequestType, enactment_level = sys.maxsize):

    rslt = Request(request_type, self, enactment_level)
    
    # a SCRUB request has no timeout, since it might have to wait for a RESILVER to finish.
    if request_type == RequestType.SCRUB:
      rslt.timer = False
    return rslt

  def request(self, request_type: RequestType, enactment_level = sys.maxsize):
    def create():
      if self.unsupported_request(request_type):
        log.debug(f"{human_readable_id(self)}: unsupported request type: {request_type}")
      request = self.prepare_request(request_type, enactment_level)
      # adding the new request to self.requested should stop the infinite recursion
      # if a dependency results in another request to this entity (such as when an ONLINE 
      # request on a ZDev triggers an ONLINE request on a ZPOOL, which then triggers
      # an ONLINE request on the Zdev again.)
      self.requested[request_type] = request
      deps = self.request_dependencies(request_type, enactment_level)
      for dep in deps:
        request.add_dependency(dep)
      return request
    if request_type in self.requested:
      log.debug(f"{human_readable_id(self)}: already requested: {request_type.name}")
      request = self.requested[request_type]
      if request.enactment_level < enactment_level:
        log.debug(f"{human_readable_id(self)}: changing enactment level: {request_type.name}")
        request.set_enactment_level(enactment_level)
      return request
    else:
      return create()


  def cancel_request(self, request_type: RequestType, reason):
    if request_type in self.requested:
      rqst = self.requested[request_type]
      log.info(f"{human_readable_id(self)} cancelling request {request_type} because: {reason}")
      rqst.cancel(reason)
    else:
      log.error(f"{human_readable_id(self)}: cannot cancel request {request_type.name}: not requested.")



  def id(self):
    raise NotImplementedError()

  def get_state(self):
    if self.is_cache:
      return self.state.what
    return cached(self).state.what

  def set_state(self, state, log_message=None, since_unknown=False):
    cache = self
    if not self.is_cache:
      cache = self.cache if self.cache is not None else cached(self)

    prev_state = cache.state.what
    now = None if since_unknown else inaccurate_now()
    if state in {EntityState.INACTIVE, EntityState.DISCONNECTED}:
      if cache.state is not None and is_online_state(cache.state.what):
        cache.last_online = now
        # TODO: move last_update transition behavior into ZDev-specific state handling.
        if hasattr(cache, "last_update") and not since_in(Operation.RESILVER, cache.operations):
          cache.last_update = now
    if prev_state == state:
      return None

    cache.state = Since(state, now)
    if prev_state is not None and log_message is not None:
      cache_log_info(cache, log_message)
    return prev_state

  def handle_disconnected(self):
    prev_state = self.set_state(EntityState.DISCONNECTED, "disconnected")
    if prev_state is None:
      return
    succeed_request(self, RequestType.OFFLINE)
    tell_parent_child_offline(self.parent, self, prev_state)



  def handle_deactivated(self):
    prev_state = self.set_state(EntityState.INACTIVE, "deactivated")
    if prev_state is None:
      return
    succeed_request(self, RequestType.OFFLINE)
    tell_parent_child_offline(self.parent, self, prev_state)
    if isinstance(self.parent, Entity):
      if cached(self.parent).state.what == EntityState.DISCONNECTED:
        self.handle_disconnected()

  def handle_appeared(self):
    prev_state = self.set_state(EntityState.INACTIVE, "appeared")
    if prev_state is not None:
      succeed_request(self, RequestType.APPEAR)




  def handle_parent_online(self, new_state=EntityState.INACTIVE):
    cache = cached(self)
    err_state = None
    if cache.state.what not in [EntityState.DISCONNECTED, EntityState.UNKNOWN] :
      err_state = cache.state.what
      new_state = cache.state.what
    if err_state:
      log.error(f"{human_readable_id(self)} was already {err_state.name}, when parent became ONLINE. This is either some inconsistency in the cache (due to events being missed when zmirror wasn't running), or a bug in zmirror. Setting new state to: {new_state.name}. Please note, that this might not fix all inconsistencies, as now we will not run the event handlers for entity.on_appeared as it would be unsafe without knowledge of the previous state.")
    prev_state = self.set_state(new_state)
    if not err_state:
      if hasattr(self, "handle_appeared"):
        self.handle_appeared()







  # must be overridden by child classes
  def get_dependencies(self, request):
    if request == RequestType.ONLINE:
      return [self.parent]
    return []





def run_event_handlers(self, event_name, excepted=None):

  if not config.event_handlers_enabled:
    log.info(f"{human_readable_id(self)}: {event_name}. Skipping event handlers (disabled)")
    return
  handlers = getattr(self, "on_" + event_name)
  if handlers:
    for event in handlers:
      if event != excepted:
        run_action(self, event)



def run_action(self, action):
  if action == "offline":
    if hasattr(self, "enact_offline"):
      if any(e in [RequestType.TRIM, RequestType.SCRUB] for e in self.requested):
        log.info(f"{human_readable_id(self)}: not taking offline since other operations are pending")
      else:
        return self.request(RequestType.OFFLINE, enactment_level=0).enact_hierarchy()
    else:
      log.error(f"{human_readable_id(self)}: entity does not support being taken offline")
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  elif action == "online":
    if hasattr(self, "enact_online"):
      return self.request(RequestType.ONLINE, enactment_level=0).enact_hierarchy()
    else:
      log.error(f"{human_readable_id(self)}: entity does not support being taken online")
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  elif action == "snapshot":
    if hasattr(self, "enact_snapshot"):
      self.request(RequestType.SNAPSHOT, enactment_level=0).enact_hierarchy()
    else:
      log.error(f"{human_readable_id(self)}: entity does not have the ability to create snapshots")
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  elif action == "scrub":
    if hasattr(self, "enact_scrub"):
      self.request(RequestType.SCRUB, enactment_level=0).enact_hierarchy()
    else:
      log.error(f"{human_readable_id(self)}: entity cannot be scrubbed")
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  elif action == "trim":
    if hasattr(self, "enact_trim"):
      self.request(RequestType.TRIM, enactment_level=0).enact_hierarchy()
    else:
      log.error(f"{human_readable_id(self)}: entity cannot be trimmed")
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE

  elif action == "snapshot-parent":
    if hasattr(self.parent, "enact_snapshot"):
      return self.parent.request(RequestType.SNAPSHOT, enactment_level=0).enact_hierarchy()
    else:
      log.error(f"{make_id(self)}: the parent entity does not have the ability to create snapshots")
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  elif action == "pass":
    # do nothing
    pass
  else:
    log.error(f"unknown event type for {make_id(self)}: {action}")
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE



def tell_parent_child_offline(parent, child, prev_state):
  if parent is not None:
    if hasattr(parent, "handle_child_offline"):
      parent.handle_child_offline(child, prev_state)



def tell_parent_child_online(parent, child, prev_state):
  if parent is not None:
    if hasattr(parent, "handle_child_online"):
      parent.handle_child_online(child, prev_state)





@dataclass
class Children(Entity):
  content: list = field(default_factory=list, kw_only=True)

  on_children_offline: list = field(default_factory=list, kw_only=True)


  def print_status(self, kdstream):
    super().print_status(kdstream)

    if self.content:
      kdstream.newline()
      print_status_many(self.content, kdstream)

  def request_dependencies(self, request_type: RequestType, enactment_level: int = sys.maxsize):
    if request_type == RequestType.OFFLINE:
      def do(entity):
        return entity.request(RequestType.OFFLINE, enactment_level - 1)
      r = list(map(do, self.content))
      return r
    elif request_type == RequestType.ONLINE:
      return super().request_dependencies(RequestType.ONLINE, enactment_level)
    elif request_type == RequestType.APPEAR:
      return super().request_dependencies(RequestType.ONLINE, enactment_level)
    else:
      raise ValueError(f"bug: request type {request_type.name} cannot be fulfilled by class `Children`")
  

  def handle_onlined(self, state=EntityState.CONNECTED):
    super().handle_onlined(state=state)
    for c in self.content:
      handle_parent_online(c)
  



  def handle_deactivated(self):
    prev_state = self.get_state()
    super().handle_deactivated()
    if self.get_state() != prev_state:
      for c in self.content:
        handle_parent_offline(c)



  def handle_disconnected(self):
    prev_state = self.get_state()
    super().handle_disconnected()
    if self.get_state() != prev_state:
      for c in self.content:
        handle_parent_offline(c)




  def handle_children_offline(self):
    self.enact_requests()
    run_event_handlers(self, "children_offline")



#  def handle_child_online(self):
#    cached(self)
#    set_cache_state(self, EntityState.CONNECTED)




  def handle_child_offline(self, _child, prev_state):

    # this change is irrelevant for the parent
    if prev_state == EntityState.INACTIVE:
      return
    # if hasattr(self, "handle_children_offline"):
    online = False
    for c in self.content:
      if is_online(c):
        online = True
        break
    if not online:
      self.handle_children_offline()

  def handle_child_online(self, _child, _prev_state):
    pass
    # handle_onlined(cached(self))



def handle_parent_online(self):

  if hasattr(self, "handle_parent_online"):
    self.handle_parent_online()

def handle_parent_offline(self):

  if hasattr(self, "handle_parent_offline"):
    self.handle_parent_offline()


def handle_online_request(self):
  if RequestType.ONLINE in self.requested:
    self.enact_online()
    return True
  return False





def possibly_force_enable_trim(self):
  if self.force_enable_trim:
    path = config.find_provisioning_mode(self.dev_path())
    if path is None:
      log.warning(f"{human_readable_id(self)}: failed to force enable trim, device (or provisioning_mode flag) not found.")
    else:
      state = read_file(path)
      if state is None:
        log.error(f"{human_readable_id(self)}: could not read provisioning_mode from: {path}")
      else:
        if state.strip() != "unmap":
          log.warning(f"{human_readable_id(self)}: force enabling trim")
          return commands.add_script(f"echo unmap > {path}")
        else:
          log.info(f"{human_readable_id(self)}: trim already enabled")




@yaml_data
class ManualChildren(Children):

  def unsupported_request(self, request_type):
    if request_type in {RequestType.ONLINE, RequestType.OFFLINE}:
      return Reason.MANUALLY_DISCONNECTED
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE



@yaml_data("disk", also_use_class_name=False)
class Disk(ManualChildren):


  uuid: str = None
  info: str = None
  ssd: bool = None

  force_enable_trim: bool = False

  @classmethod
  def id_fields(cls):
    return ["uuid"]




  def handle_appeared(self):
    raise NotImplementedError(f"`{type(self).__name__}`s do not appear, they can only be ONLINE or DISCONNECTED")
  
  def handle_onlined(self, state=EntityState.CONNECTED):
    prev_state = self.get_state()
    if any(is_online(child) for child in self.content):
      state = EntityState.ACTIVE
    super().handle_onlined(state=state)
    if self.get_state() != prev_state:
      possibly_force_enable_trim(self)

  def handle_child_online(self, _child, _prev_state):
    if self.get_state() == EntityState.CONNECTED:
      self.set_state(EntityState.ACTIVE, "activated")

  def handle_children_offline(self):
    if self.get_state() == EntityState.ACTIVE:
      self.set_state(EntityState.CONNECTED, "deactivated")
    return super().handle_children_offline()


  # this requires a udev rule to be installed which ensures that the disk appears under its GPT partition table UUID under /dev/disk/by-uuid
  def dev_path(self):
    return f"/dev/disk/by-uuid/{self.uuid}"

  def load_initial_state(self):
    return load_disk_or_partition_initial_state(self)

  def finalize_init(self):
    if self.ssd is None:
      self.ssd = getattr(config.config_root, "ssd", True)
    if is_present_or_online(cached(self)):
      possibly_force_enable_trim(self)


  def id(self):
    if self.uuid is not None:
      return make_id(self, uuid=self.uuid)
    else:
      raise ValueError("uuid not set")

  def hrid(self):
    type_name = get_name_for_type(type(self))
    return f"{type_name}: {self.info or '-'}"



@yaml_data("part", also_use_class_name=False)
class Partition(ManualChildren):
  name: str = None





  @classmethod
  def id_fields(cls):
    return ["name"]


  def handle_onlined(self, state=EntityState.CONNECTED):
    if any(is_online(child) for child in self.content):
      state = EntityState.ACTIVE
    super().handle_onlined(state=state)

  def handle_child_online(self, _child, _prev_state):
    if self.get_state() == EntityState.CONNECTED:
      self.set_state(EntityState.ACTIVE, "activated")

  def handle_children_offline(self):
    if self.get_state() == EntityState.ACTIVE:
      self.set_state(EntityState.CONNECTED, "deactivated")
    return super().handle_children_offline()



  def dev_path(self):
    return f"/dev/disk/by-partlabel/{self.name}"

  def load_initial_state(self):

    return load_disk_or_partition_initial_state(self)






  def id(self):
    return make_id(self, name=self.name)


def load_disk_or_partition_initial_state(self):
  if config.dev_exists(self.dev_path()):
    if any(is_online(child) for child in self.content):
      return EntityState.ACTIVE
    return EntityState.CONNECTED
  return EntityState.DISCONNECTED



@yaml_data
class BackingDevice:
  device: Any
  required: bool = False
  online_dependencies: bool = True

  
  def unsupported_request(self, request_type):
    return self.device.unsupported_request(request_type)
  
  def state_allows(self, request_type):
    return self.device.state_allows(request_type)

  def request(self, request_type, enactment_level: int = sys.maxsize):
    return self.device.request(request_type, enactment_level)

  def get_state(self):
    return self.device.get_state()

  def remove_request(self, request_type):
    return self.device.remove_request(request_type)






def unavailable_guard(blockdevs, devname):
  if devname in blockdevs:
    return blockdevs[devname]
  else:
    return UnavailableDependency(name=devname)





@yaml_data
class DevicesAgregate(Entity):

  pool = None

  requested: dict = field(default_factory=dict)


  def id(self):
    return (type(self), {"pool": self.pool.name})
  
  @classmethod
  def id_fields(cls):
    return ["pool"]

  def is_fulfilled(self, request):
    # this is managed by the request itself, a DevicesAgregate does not track request fulfillment
    return request.check_dependencies()


  def unsupported_request(self, request_type):
    if request_type in {RequestType.ONLINE, RequestType.APPEAR}:
      return None
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE
  
  def state_allows(self, request_type):
    # since DevicesAggregates cannot enact any requests themselves
    # there is also no state that could possibly allow for any enactments
    return False

  devices: list = field(default_factory=list)

  def prepare_request(self, request_type, enactment_level):
    raise NotImplementedError()

  def request_dependencies(self, request_type: RequestType, enactment_level = sys.maxsize):
    if request_type in {RequestType.ONLINE, RequestType.APPEAR}:
      return [d.request(request_type, enactment_level - 1) for d in self.devices]
    else:
      raise ValueError(f"{human_readable_id(self.entity)}: bug: unsupported request type for backing: {request_type.name}")


  def get_state(self):
    one_online = False
    one_inactive = False
    one_required_inactive = False
    one_required_offline = False
    for d in self.devices:
      state = d.get_state()

      if state == EntityState.INACTIVE:
        one_inactive = True
        if d.required:
          one_required_inactive = True
      elif is_online_state(state):
        one_online = True
      elif state == EntityState.DISCONNECTED or state == EntityState.UNKNOWN:
        if d.required:
          one_required_offline = True
    if one_required_offline:
      return EntityState.DISCONNECTED
    if one_required_inactive:
      return EntityState.INACTIVE
    if one_online:
      return EntityState.CONNECTED
    if one_inactive:
      return EntityState.INACTIVE

@yaml_data("mirror", also_use_class_name=False)
class Mirror(DevicesAgregate):

  def prepare_request(self, request_type, enactment_level):
    return MirrorRequest(request_type, self, enactment_level)

  def init(self, pool, blockdevs):
    init_backing(self, pool, blockdevs)
    for d in self.devices:
      if isinstance(d, BackingDevice):
        d.device.is_mirror = True

  def get_state(self):
    one_online = False
    one_inactive = False
    one_required_inactive = False
    one_required_offline = False
    for d in self.devices:
      state = d.get_state()

      if state == EntityState.INACTIVE:
        one_inactive = True
        if hasattr(d, "required") and d.required:
          one_required_inactive = True
      elif is_online_state(state):
        one_online = True
      elif state == EntityState.DISCONNECTED or state == EntityState.UNKNOWN:
        if hasattr(d, "required") and d.required:
          one_required_offline = True
    if one_required_offline:
      return EntityState.DISCONNECTED
    if one_required_inactive:
      return EntityState.INACTIVE
    if one_online:
      return EntityState.CONNECTED
    if one_inactive:
      return EntityState.INACTIVE




@dataclass
class ParityRaid(DevicesAgregate):
  parity: int = None

  def prepare_request(self, request_type, enactment_level):
    return RaidRequest(request_type, self, enactment_level, parity=self.parity)
  

  def init(self, parent, blockdevs):
    init_backing(self, parent, blockdevs)



def init_backing(self: DevicesAgregate, pool, blockdevs):
  self.pool = pool
  for i, dev in enumerate(self.devices):
    if isinstance(dev, str):
      self.devices[i] = BackingDevice(unavailable_guard(blockdevs, dev))
    else:
      if not "name" in dev:
        raise ValueError(f"misconfiguration: backing for {human_readable_id(pool)}. `name` missing in Mirror.")
      self.devices[i] = BackingDevice(
        unavailable_guard(blockdevs, dev["name"]),
        yes_no_absent_or_dict(dev, "required", False, f"misconfiguration: backing for {human_readable_id(pool)}"),
        yes_no_absent_or_dict(dev, "online_dependencies", True, f"misconfiguration: backing for {human_readable_id(pool)}")
      )


@yaml_data("zpool", also_use_class_name=False)
class ZPool(Onlineable, Children):
  name: str = None
  errors: bool = field(metadata={"db": True}, default=False)

  root: str = None
  zpool_import_args: str = None

  mount: bool = True

  backed_by: list = field(default_factory=list)

  on_backing_appeared: list = field(default_factory=list)


  _backed_by: list = None

  @classmethod
  def id_fields(cls):
    return ["name"]
  
  
  def state_allows(self, request_type):
    state = cached(self).state.what
    if is_online_state(state) and request_type in [RequestType.OFFLINE, RequestType.TRIM, RequestType.SCRUB]:
      return True
    # a zpool is never INACTIVE, it is only ever DISCONNECTED, and whether
    # the state allows a request, depends solely on the request this 
    # request depends on (namely requests bringing zdevs online)
    elif state == EntityState.DISCONNECTED and request_type == RequestType.ONLINE:
      return True
    return False
  

  # def handle_appeared(self, prev_state):
  #  pass

  

  def unsupported_request(self, request_type: RequestType):
    if request_type in [RequestType.OFFLINE, RequestType.ONLINE, RequestType.SCRUB, RequestType.TRIM]:
      return None
    return Children.unsupported_request(self, request_type)


  def request_dependencies(self, request_type, enactment_level: int = sys.maxsize):
    def request_backing(type):
      def do(backing):
        return backing.request(type, enactment_level - 1)
      return list(map(do, self.backed_by))
    if request_type == RequestType.ONLINE:
      return request_backing(RequestType.APPEAR)
    elif request_type == RequestType.SCRUB:
      return request_backing(RequestType.ONLINE)
    else:
      return super().request_dependencies(request_type, enactment_level= enactment_level)



  def print_status(self, kdstream):
    Entity.print_status(self, kdstream)

    kdstream.newline()
    kdstream.print_property(cached(self), "errors")

    if self.name in config.zfs_blockdevs:

      def get_name(entity):
        return entity.name

      devs = config.zfs_blockdevs[self.name]
      if devs:
        devs = devs.values()
        devs = sorted(devs, key=get_name)

        kdstream.newline()
        kdstream.print_property_prefix("backing")
        kdstream.print_raw(" [:")
        kdstream.indent()
        print_status_many(devs, kdstream)
        kdstream.dedent()

    if self.content:
      kdstream.newline()
      kdstream.print_property_prefix("backing")
      kdstream.print_raw(" [:")
      kdstream.indent()
      print_status_many(self.content, kdstream)
      kdstream.dedent()


  def id(self):
    return make_id(self, name=self.name)


  def handle_backing_device_appeared(self):
    if (not is_online(self)) and self.run_on_backing(is_present_or_online):
      self.enact_requests()
      run_event_handlers(self, "backing_appeared")

  def _is_content_effectively_online(self, entity):
    if isinstance(entity, ZFSVolume):
      for child in entity.content:
        if is_online(child):
          return True
      return False
    if is_online(entity):
      return True
    return False

  def handle_child_offline(self, child, prev_state):
    if prev_state == EntityState.INACTIVE:
      return
    for content in self.content:
      if self._is_content_effectively_online(content):
        return
    self.handle_children_offline()

  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    status = config.get_zpool_status(self.name)
    if status is not None:
      state = EntityState.CONNECTED
    return state

  def finalize_init(self):
    if self.zpool_import_args is None:
      self.zpool_import_args = config.config_root.zpool_import_args
    # empty string explicitly means "no args" and should override root inheritance.
    if isinstance(self.zpool_import_args, str):
      normalized = self.zpool_import_args.strip()
      if normalized == "" or normalized.lower() in {"nil", "none", "void"}:
        self.zpool_import_args = None
      else:
        self.zpool_import_args = normalized

    backed = self.backed_by if self.backed_by is not None else []
    self._backed_by = backed
    if self.name in config.zfs_blockdevs:
      devs = config.zfs_blockdevs[self.name]
    else:
      devs = dict()

    for i, b in enumerate(backed):
      if isinstance(b, str):
        if b in devs:
          backed[i] = BackingDevice(device = devs[b], required=True, online_dependencies=True)
        else:
          backed[i] = UnavailableDependency(name=b)
      else:
        b.init(self, devs)




  def enact_scrub(self):
    self.stop_scrub()
    return commands.add_script(f"zpool scrub {self.name}", unless_redundant = True)

  def stop_scrub(self):
    return commands.add_script(f"zpool scrub -s {self.name}", unless_redundant = True)


  def enact_trim(self):
    self.stop_scrub()
    return commands.add_script(f"zpool trim {self.name}", unless_redundant = True)

  def stop_trim(self):
    return commands.add_script(f"zpool trim -s {self.name}", unless_redundant = True)



  def enact_cancel_scrub(self):
    return self.stop_scrub()


  def enact_cancel_trim(self):
    return self.stop_trim()

  def enact_offline(self):
    return commands.add_script(f"zpool export {self.name}", unless_redundant = True)

  def enact_online(self):
    if is_online(self):
      log.debug(f"zpool {self.name} already online")
      return fulfilled_promise()

    sufficient = self.run_on_backing(is_present_or_online)
    if sufficient:
      log.info(f"{human_readable_id(self)}: sufficient backing devices available, importing zpool.")
      import_args = f" {self.zpool_import_args}" if self.zpool_import_args else ""
      root = f" -R {self.root}" if self.root else ""
      nomount = f"" if self.mount else " -N"
      return commands.add_script(f"set -e\nudevadm settle\nzpool import{import_args} {self.name}{root}{nomount}", unless_redundant = True)
    else:
      log.info(f"{human_readable_id(self)}: insufficient backing devices available, or per-configuration required backing devices unavailable.")


  def run_on_backing(self, fn):
    sufficient = True
    for b in self._backed_by:
      if not fn(b):
        sufficient = False
    return sufficient





# TODO capture online/offline events and write tests for this one
@yaml_data
class ZFSDataset(Entity):
  pool: str = None
  name: str = None


  on_appeared: list = field(default_factory=list)


  @classmethod
  def id_fields(cls):
    return ["pool", "name"]


  def unsupported_request(self, request_type):
    if request_type not in {RequestType.ONLINE, RequestType.OFFLINE, RequestType.SNAPSHOT}:
      return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE

  def request_dependencies(self, request_type, enactment_level = sys.maxsize):
    if request_type == RequestType.SNAPSHOT:
      return [self.request(RequestType.ONLINE, enactment_level = -1)]
    return super().request_dependencies(request_type, enactment_level)

  def id(self):
    return make_id(self, pool=self.get_pool(), name=self.name)

  def state_allows(self, request_type):
    state = cached(self).state.what
    if is_online_state(state) and request_type == RequestType.SNAPSHOT:
      return True
    return super().state_allows(request_type)

  def handle_appeared(self):
    super().handle_appeared()
    self.enact_requests()
    run_event_handlers(self, "appeared")


  def handle_parent_online(self, new_state=EntityState.INACTIVE):
    state = self.load_initial_state()
    if state == EntityState.INACTIVE:
      handle_appeared(cached(self))
    elif is_online_state(state):
      handle_onlined(cached(self))
    else:
      log.error(f"{human_readable_id(self)}: inconsistent initial state ({state}). This is likely due to a misconfiguration.")


  def get_pool(self):
    if self.parent is not None:
      return self.parent.name
    else:
      return self.pool

  def load_initial_state(self):
    zfs_state = config.get_zfs_mounted(f"{self.get_pool()}/{self.name}")
    if zfs_state == "yes":
      return EntityState.CONNECTED
    elif zfs_state == "no":
      return EntityState.INACTIVE
    else:
      return EntityState.DISCONNECTED

  def enact_online(self):
    return commands.add_script(f"zfs mount {self.parent.name}/{self.name}")

  def enact_offline(self):
    return commands.add_script(f"zfs umount {self.parent.name}/{self.name}")

  def enact_snapshot(self):
    return commands.add_script(f"zfs snapshot {self.parent.name}/{self.name}@zmirror-{inaccurate_now().strftime("%Y-%m-%d_%H-%M-%S")}")



@yaml_data("zvol", also_use_class_name=False)
class ZFSVolume(ManualChildren):
  pool: str = None
  name: str = None


  on_appeared: list = field(default_factory=list)

  @classmethod
  def id_fields(cls):
    return ["pool", "name"]

  def hrid(self):
    type_name = get_name_for_type(type(self))
    zvol_name = self.name or "-"
    pool_name = self.get_pool()
    if pool_name:
      return f"{type_name}: {zvol_name} ({pool_name})"
    return f"{type_name}: {zvol_name}"


  def unsupported_request(self, request_type):
    if request_type in {RequestType.ONLINE, RequestType.OFFLINE, RequestType.SNAPSHOT}:
      return None
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE

  def request_dependencies(self, request_type, enactment_level = sys.maxsize):
    if request_type == RequestType.SNAPSHOT:
      return [self.request(RequestType.ONLINE, enactment_level = -1)]
    return super().request_dependencies(request_type, enactment_level)

  def id(self):
    return make_id(self, pool=self.get_pool(), name=self.name)

  def state_allows(self, request_type):
    state = cached(self).state.what
    if is_online_state(state) and request_type == RequestType.SNAPSHOT:
      return True
    return super().state_allows(request_type)

  def handle_appeared(self):
    super().handle_appeared()
    self.enact_requests()
    run_event_handlers(self, "appeared")

  def handle_onlined(self, state=EntityState.CONNECTED):
    if any(is_online(child) for child in self.content):
      state = EntityState.ACTIVE
    super().handle_onlined(state=state)

  def handle_child_offline(self, child, prev_state):
    super().handle_child_offline(child, prev_state)
    tell_parent_child_offline(self.parent, self, prev_state)

  def handle_child_online(self, child, prev_state):
    if self.get_state() == EntityState.CONNECTED:
      self.set_state(EntityState.ACTIVE, "activated")
    tell_parent_child_online(self.parent, self, prev_state)

  def handle_children_offline(self):
    if self.get_state() == EntityState.ACTIVE:
      self.set_state(EntityState.CONNECTED, "deactivated")
    return super().handle_children_offline()

  def handle_parent_online(self, _new_state=EntityState.CONNECTED):
    handle_onlined(cached(self))

  def handle_parent_offline(self, _new_state=EntityState.DISCONNECTED):
    handle_disconnected(cached(self))


  def get_pool(self):
    if self.parent is not None:
      return self.parent.name
    else:
      return self.pool

  def update_initial_state(self):
    if self.parent is None:
      return EntityState.DISCONNECTED
    parent_state = cached(self.parent).state.what
    if is_online_state(parent_state):
      if any(is_online(child) for child in self.content):
        return EntityState.ACTIVE
      return EntityState.CONNECTED
    return EntityState.DISCONNECTED

  def enact_snapshot(self):
    return commands.add_script(f"zfs snapshot {self.parent.name}/{self.name}@zmirror-{inaccurate_now().strftime("%Y-%m-%d_%H-%M-%S")}")


  def dev_path(self):
    if self.parent is not None:
      return f"/dev/zvol/{self.parent.name}/{self.name}"
    else:
      return f"/dev/zvol/{self.pool}/{self.name}"


# an entity that is embedded inside another and thus must be notified by its parent (zdevs and dmcrypts)
class Embedded:

  def unsupported_request(self, request_type):
    # this is a bit of a hack
    # embedded entities "support" the request type apppear
    # so that at the point when the parent's ONLINE event
    # is being handled, but the child's APPEAR event has
    # not been triggered, the event won't fail.

    if request_type == RequestType.APPEAR:
      return None
    return super().unsupported_request(self, request_type)

  def handle_parent_offline(self, _new_state=EntityState.INACTIVE):
    state = cached(self).state.what
    if is_online_state(state):
      log.info(f"{human_readable_id(self)}: parent OFFLINE, requesting OFFLINE.")
      request = self.request(RequestType.OFFLINE)
      request.enact_hierarchy()
    elif state == EntityState.INACTIVE:
      handle_disconnected(self)


@yaml_data("crypt", also_use_class_name=False)
class DMCrypt(Onlineable, Embedded, Children):
  name: str = None
  key_file: str = None

  @classmethod
  def id_fields(cls):
    return ["name"]

  on_appeared: list = field(default_factory=list)




  def id(self):
    return make_id(self, name=self.name)

  def dev_path(self):
    return f"/dev/mapper/{self.name}"


  def handle_appeared(self):
    super().handle_appeared()
    self.enact_requests()
    run_event_handlers(self, "appeared")


  def handle_child_online(self, child, prev_state):
    if self.get_state() == EntityState.CONNECTED:
      self.set_state(EntityState.ACTIVE, "activated")

  def handle_children_offline(self):
    if self.get_state() == EntityState.ACTIVE:
      self.set_state(EntityState.CONNECTED, "deactivated")
    return super().handle_children_offline()

  def load_initial_state(self):
    if config.dev_exists(self.dev_path()):
      if any(is_online(child) for child in self.content):
        return EntityState.ACTIVE
      return EntityState.CONNECTED
    return EntityState.UNKNOWN

  def update_initial_state(self):
    if not is_online_state(cached(self).state.what):
      state = EntityState.DISCONNECTED
      if hasattr(self.parent, "state"):
        cp = cached(self.parent)
        if is_present_or_online_state(cp.state.what):
          state = EntityState.INACTIVE
      return state


  def enact_offline(self):
    return commands.add_script(f"cryptsetup close {self.name}")

  def enact_online(self):
    if self.key_file:
      return commands.add_script(f"cryptsetup open {self.parent.dev_path()} {self.name} --key-file {self.key_file}")
    else:
      trials = 3
      def on_error(exception: Exception):
        nonlocal trials
        import traceback
        ex = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        trials -= 1
        log.error(f"opening dm-crypt failed. Remaining trys: {trials}")
        if trials > 0:
          return request_password()
        else:
          raise exception
      def on_password_given(rslt):
        _cmd, _code, outs, _outr = rslt
        pw = "\n".join(outs)
        log.info(f"password received successfully")
        rslt = commands.add_script(f"cryptsetup open {self.parent.dev_path()} {self.name}", input=pw + "\n").then(None, on_error)
        return rslt
      def request_password():
        nonlocal trials
        def on_reject(exc):
          log.error("password request cancelled (or ssh-askpass not available)")
          raise exc
        if config.running:
          return commands.add_script(f"DISPLAY=:0 ssh-askpass 'zmirror: encryption key for: {backslash_escape("'", human_readable_id(self))} (remaining trys: {trials})'").then(on_password_given, on_reject)
          # return commands.add_script(f"systemd-ask-password --id='zmirror:{backslash_escape("'",entity_id_string(self))}' --timeout=60 --user --echo=masked 'zmirror: encryption key for: {backslash_escape("'", human_readable_id(self))} (remaining trys: {trials})'").then(on_password_given, on_error)
        else:
          raise ValueError("zmirror is shutting down")
      return request_password()
      
  


def run_get_password_command(entity, handler):
  cmd = None
  if shutil.which('systemd-ask-password') is not None:
    cmd = f'systemd-ask-password --id "zmirror:{entity_id_string(entity)}" "zmirror: please enter key for: {human_readable_id(entity)}"'
  else:
    raise ValueError("no password requesting binary found")

  # TODO implement properly
  commands.add_script(cmd)


def uncached(cache, fn=None):
  if not cache.is_cache:
    cache = cached(cache)
  entity = config.load_config_for_cache(cache)
  if entity is None:
    log.debug(f"entity not configured: {entity_id_string(cache)}")
    return
  entity.cache = cache

  if fn:
    return fn(entity)
  else:
    return entity


def uncached_operation_handle_by_name(cache, name):
  def do(entity):
    method = getattr(entity, "handle_" + name)
    method()
  uncached(cache, do)


def uncached_userevent_by_name(cache, name):
  def do(entity):
    run_event_handlers(entity, name)
  uncached(cache, do)

def inaccurate_now():
  return datetime.now().replace(microsecond=0)

# zmirror assumes a mirrored device that was just onlined (via zpool online)
# is in "resilvering" state right away. This assumption is a simplification
# so that zmirror does not assume that other operations can be run (e.g. scrub).
#
# It is a simplification because ZFS itself only starts a resilver some seconds
# after the device was onlined.
#
# We could also have implemented another state named BEFORE_RESILVER
# but that would have complicated the zmirror's application logic tremendously.
#
# Also we would have to distinguish between mirrored and non-mirrored devices
# anyways, because a non-mirrored device should never enter the BEFORE_RESILVER
# state.
#
# So the simplification is warrented.
def handle_resilver_started(cache):
  cache = cached(cache)
  if not since_in(Operation.RESILVER, cache.operations):
    cache.operations.append(Since(Operation.RESILVER, inaccurate_now()))
    cache_log_info(cache, "resilver started")
  if cache.state.what != EntityState.ACTIVE:
    cache.set_state(EntityState.ACTIVE)
  cache.last_online = inaccurate_now()


# used for zdevs when brought online via zpool online (instead of zpool import)
def handle_zdev_onlined(cache):
  zdev = uncached(cache)
  if not zdev:
    log.verbose(f"{human_readable_id(cache)}: ONLINE. Unconfigured, not assuming that it starts resilvering.")
    handle_onlined(cache)
  else:
    if zdev.is_mirror:
      log.verbose(f"{human_readable_id(cache)}: ONLINE. This is (configured as) a mirror device, assuming resilver started.")
      handle_resilver_started(cache)
    else:
      log.verbose(f"{human_readable_id(cache)}: ONLINE. This is not (configured as) a mirror device, assuming that no resilvering is happening.")
      handle_onlined(cache)


def handle_resilver_finished(cache):
  cache = cached(cache)
  if cache.state.what != EntityState.ACTIVE:
    cache.set_state(EntityState.ACTIVE)
  cache_log_info(cache, "resilvered (updated)")
  cache.last_online = cache.last_update = inaccurate_now()
  since_remove(Operation.RESILVER, cache.operations)
  uncached_operation_handle_by_name(cache, "resilver_finished")


def handle_scrub_started(cache):
  cache_log_info(cache, "scrub started")
  since_insert_if_not_in(Since(Operation.SCRUB, inaccurate_now()), cache.operations)
  def do(entity):
    entity.handle_scrub_started()
  uncached(cache, do)


def handle_scrub_finished(cache, successful_scrub=False):
  was_scrubbing = since_in(Operation.SCRUB, cache.operations)
  successful_scrub = successful_scrub and was_scrubbing
  if successful_scrub:
    cache_log_info(cache, "successfully scrubbed")
  else:
    cache_log_info(cache, "scrub finished with errors")
  since_remove(Operation.SCRUB, cache.operations)
  if successful_scrub:
    cache.last_scrub = inaccurate_now()
  def do(entity):
    entity.handle_scrub_finished(successful_scrub)
  uncached(cache, do)



def handle_trim_started(cache):
  cache_log_info(cache, "trim started")
  since_insert_if_not_in(Since(Operation.TRIM, inaccurate_now()), cache.operations)
  def do(entity):
    entity.handle_trim_started()
  uncached(cache, do)


def handle_trim_finished(cache):
  cache_log_info(cache, "trimmed")
  now = inaccurate_now()
  since_remove(Operation.TRIM, cache.operations)
  cache.last_trim = now
  def do(entity):
    entity.handle_trim_finished()
  uncached(cache, do)


def handle_scrub_canceled(cache):
  cache_log_info(cache, "scrub canceled")
  since_remove(Operation.SCRUB, cache.operations)
  uncached_userevent_by_name(cache, "scrub_canceled")


def handle_trim_canceled(cache):
  cache_log_info(cache, "trim canceled")
  since_remove(Operation.TRIM, cache.operations)
  uncached_userevent_by_name(cache, "trim_canceled")



def cache_log_info(cache, message):
  entity = uncached(cache)
  if entity is not None:
    log.info(f"{human_readable_id(entity)}: {message}")
  else:
    log.verbose(f"{entity_id_string(cache)} (unconfigured): {message}")


# the device or zpool has been taken offline and is not even passively available (it must be reactivated somehow)
def handle_disconnected(cache):
  cache = cached(cache)
  entity = uncached(cache)
  if entity is None:
    cache.set_state(EntityState.DISCONNECTED, "disconnected")
    return
  entity.handle_disconnected()

# the device is still passively available
def handle_deactivated(cache):
  cache = cached(cache)
  entity = uncached(cache)
  if entity is None:
    cache.set_state(EntityState.INACTIVE, "deactivated")
    return
  entity.handle_deactivated()

# the device became passively available
def handle_appeared(cache):
  cache = cached(cache)
  entity = uncached(cache)
  if entity is None:
    cache.set_state(EntityState.INACTIVE, "appeared")
    return
  entity.handle_appeared()

# the device has activated
def handle_onlined(cache):
  cache = cached(cache)
  entity = uncached(cache)
  if entity is None:
    state = EntityState.ACTIVE if cache.state.what == EntityState.ACTIVE else EntityState.CONNECTED
    cache.set_state(state, "onlined")
    return
  entity.handle_onlined()





@yaml_data("unavailable-dependency", also_use_class_name=False)
class UnavailableDependency(Entity):

  name: str = None

  @classmethod
  def id_fields(cls):
    return ["name"]

  def id(self):
    return make_id(self, name = self.name)


  def request_dependencies(self, request_type, enactment_level: int = sys.maxsize):
    return []

  def request(self, request_type, enactment_level: int = sys.maxsize):
    request = super().request(request_type, enactment_level)
    request.fail(Reason.NOT_CONFIGURED)
    return request
    



def print_status(entity, kdstream):
  kdstream.print_class_name(entity)
  kdstream.indent()
  entity.print_status(kdstream)
  kdstream.dedent()

def print_status_many(lst, kdstream):
  for c in lst:

    kdstream.newlines(2)
    print_status(c, kdstream)


def get_attr_or_ancestor(self, attr):
  if hasattr(self, attr):
    value = getattr(self, attr)
    if value is not None:
      return value
  if hasattr(self, "parent"):
    parent = getattr(self, "parent")
    if parent is not None:
      get_attr_or_ancestor(parent, attr)



def succeed_request(self, request_type):
  if request_type in self.requested:
    request = self.requested[request_type]
    request.succeed()


def is_anything_overdue(self):
  for op in Operation:
    if hasattr(self, "is_overdue") and self.is_overdue(op):
      return True
  return False


@yaml_data("zdev", also_use_class_name=False)
class ZDev(Onlineable, Embedded, Entity):
  pool: str = field(default=None)
  name: str = field(default=None)


  on_appeared: list = field(default_factory=list)

  operations: list = field(metadata={"db": True}, default_factory=list)

  last_online: datetime = field(metadata={"db": True}, default=None)
  last_update: datetime = field(metadata={"db": True}, default=None)
  last_scrub: datetime = field(metadata={"db": True}, default=None)
  last_trim: datetime = field(metadata={"db": True}, default=None)
  errors: bool = field(metadata={"db": True}, default=False)


  on_trimmed: list = field(default_factory=list)
  on_scrub_succeeded: list = field(default_factory=list)
  on_scrub_failed: list = field(default_factory=list)
  on_scrub_finished: list = field(default_factory=list)
  on_scrub_canceled: list = field(default_factory=list)
  on_trim_canceled: list = field(default_factory=list)
  on_resilvered: list = field(default_factory=list)

  scrub_interval: str = None
  trim_interval: str = None
  update_interval: str = None
  available_update_interval: str = None

  is_mirror: bool = False

  @classmethod
  def id_fields(cls):
    return ["pool", "name"]
  

  def get_last_update(self):
    cache = cached(self)
    now = inaccurate_now()
    if is_online_state(cache.state.what) and not since_in(Operation.RESILVER, cache.operations):
      cache.last_update = now
      return KiSymbol("now")
    return cache.last_update
  

  def unsupported_request(self, request_type: RequestType):
    if request_type in [RequestType.OFFLINE, RequestType.ONLINE, RequestType.SCRUB, RequestType.TRIM]:
      return None
    return Embedded.unsupported_request(self, request_type)

  def handle_onlined(self, state=EntityState.ACTIVE):
    super().handle_onlined(state=state)


  def state_allows(self, request_type: RequestType):
    cache = cached(self)
    if is_online_state(cache.state.what):
      if request_type == RequestType.SCRUB:
        if not since_in(Operation.RESILVER, cache.operations):
          return True
      elif request_type == RequestType.TRIM:
        return True
    return super().state_allows(request_type)
    
  
  def finalize_init(self):
    def inherited_trim_interval():
      root_trim_interval = getattr(config.config_root, "trim_interval", None)
      if root_trim_interval is None:
        return None

      current = getattr(self, "parent", None)
      disk = None
      while current is not None:
        if isinstance(current, Disk):
          disk = current
          break
        current = getattr(current, "parent", None)

      if disk is None:
        effective_ssd = getattr(config.config_root, "ssd", True)
      elif disk.ssd is None:
        effective_ssd = getattr(config.config_root, "ssd", True)
      else:
        effective_ssd = disk.ssd

      if effective_ssd:
        return root_trim_interval
      return None

    for op in Operation:
      prop_name = f"{name_for_operation[op]}_interval"
      val = getattr(self, prop_name)
      if val is None:
        if op == Operation.TRIM:
          val = inherited_trim_interval()
        else:
          val = getattr(config.config_root, prop_name)
      if val is not None and val.lower() in {"nil", "none", "void"}:
        val = None
      setattr(self, prop_name, val)

    if self.available_update_interval is None:
      self.available_update_interval = getattr(config.config_root, "available_update_interval", None)
    if self.available_update_interval is not None and self.available_update_interval.lower() in {"nil", "none", "void"}:
      self.available_update_interval = None

  def effective_interval(self, op: Operation):
    return self.configured_interval(op)
  

  def configured_interval(self, op: Operation):
    return getattr(self, f"{name_for_operation[op]}_interval")

  def effective_available_update_interval(self):
    return self.available_update_interval
  
  def last(self, op: Operation):
    cache = cached(self)
    name = get_last_property_name_for_operation(op)
    return getattr(cache, name)

  
  def is_overdue(self, op: Operation):
    overdue_since = self._overdue_since(self.effective_interval(op), op=op)
    if overdue_since and op == Operation.RESILVER:
      cache = cached(self)
      if is_online_state(cache.state.what) and not since_in(Operation.RESILVER, cache.operations):
        return False
    return overdue_since

  def is_available_update_overdue(self):
    return self._overdue_since(self.effective_available_update_interval(), op=Operation.RESILVER)

  def _overdue_since(self, interval, op: Operation):
    if interval is None:
      return False

    cache = cached(self)
    now = inaccurate_now()
    allowed_delta_since = dateparser.parse(interval)
    if allowed_delta_since is None:
      return False
    allowed_delta = now - allowed_delta_since

    last = self.last(op)
    if last is None:
      if cache.added is None:
        base = now
      else:
        base = datetime.fromtimestamp(cache.added)
    else:
      base = last

    overdue_for = now - (base + allowed_delta)
    if overdue_for <= timedelta(0):
      return False

    overdue_since = now - overdue_for
    if overdue_since.microsecond > 0:
      overdue_since = overdue_since + timedelta(seconds=1)
    return overdue_since.replace(microsecond=0)

  def handle_resilver_finished(self):

    run_event_handlers(self, "resilvered")


  def print_status(self, kdstream):
    Entity.print_status(self, kdstream)
    cache = cached(self)
    
    
    for op in Operation:
      kdstream.newline()
      if op is Operation.RESILVER:
        kdstream.print_property_prefix("last_update")
        last_update = self.get_last_update()
        kdstream.print_obj(last_update, nil=KiSymbol("never"))
        if self.is_available_update_overdue():
          kdstream.print_raw(" # AVAILABLE OVERDUE")
      else:
        kdstream.print_property(cache, get_last_property_name_for_operation(op), nil=KiSymbol("never"))
      if self.is_overdue(op):
        kdstream.print_raw(" # OVERDUE")
      kdstream.print_property(self, f"{name_for_operation[op]}_interval", hide_if_empty=True)
      if op is Operation.RESILVER:
        kdstream.print_property(self, "available_update_interval", hide_if_empty=True)

    if cache.operations:
      kdstream.newline()
      kdstream.print_property(cache, "operations")


  def is_fulfilled(self, request: Request):
    cache = cached(self)
    for op in cache.operations:
      if operation_corresponds_to_request(op.what, request.request_type):
        return True
    return super().is_fulfilled(request)
  



  def id(self):
    return make_id(self, pool=self.pool, name=self.dev_name())

  def dev_name(self):
    def do():
      if isinstance(self.parent, Partition):
        return self.parent.name
      elif isinstance(self.parent, DMCrypt):
        return self.parent.name
      elif isinstance(self.parent, ZFSVolume):
        return f"zvol/{self.parent.parent.name}/{self.parent.name}"
      else:
        return self.name
    self.name = do()
    return self.name



  def request_dependencies(self, request_type, enactment_level: int = sys.maxsize):
    if request_type == RequestType.SCRUB:
      return [self.request(RequestType.ONLINE)]
    elif request_type == RequestType.TRIM:
      return [self.request(RequestType.ONLINE)]
    elif request_type == RequestType.OFFLINE:
      return []
    elif request_type == RequestType.APPEAR:
      return [self.parent.request(RequestType.ONLINE, enactment_level - 1)]
    elif request_type == RequestType.ONLINE:
      pool = config.find_config(ZPool, name=self.pool)
      if pool is None:
        log.error(f"{human_readable_id(self)}: pool {self.pool} not configured.")
        pool = UnavailableDependency(name=f"UNCONFIGURED: {entity_id_string(self)}")
      pool_enactment = enactment_level - 1
      return [self.parent.request(RequestType.ONLINE, enactment_level - 1), pool.request(RequestType.ONLINE, pool_enactment)]
    else:
      raise ValueError(f"{human_readable_id(self)}: unsupported request type: {request_type.name}")





  def load_initial_state(self):
    state = config.get_zpool_backing_device_state(self.pool, self.dev_name())
    if state is None:
      state = EntityState.DISCONNECTED
      opers = set()
    else:
      state, opers = state
    if is_online_state(state):
      state = EntityState.ACTIVE
    else:
      dev = self.parent.dev_path()
      if config.dev_exists(dev):
        state = EntityState.INACTIVE
      else:
        state = EntityState.DISCONNECTED
    cache = cached(self)
    for org_oper in cache.operations.copy():
      if org_oper.what not in opers:
        since_remove(org_oper.what, cache.operations)
    for oper in opers:
      if not since_in(oper, cache.operations):
        cache.operations.append(Since(oper, None))
    return state

  def handle_appeared(self):
    super().handle_appeared()
    pool_id = make_id_string(ZPool, name=self.pool)
    if pool_id in config.config_dict:
      config.config_dict[pool_id].handle_backing_device_appeared()
    run_event_handlers(self, "appeared")

  def handle_scrub_started(self):
    succeed_request(self, RequestType.SCRUB)

  def handle_scrub_canceled(self):
    succeed_request(self, RequestType.CANCEL_SCRUB)
    run_event_handlers(self, "scrub_canceled")

  def handle_scrub_finished(self, successful_scrub=False):
    succeed_request(self, RequestType.SCRUB)
    if successful_scrub:
      run_event_handlers(self, "scrub_succeeded")
    else:
      run_event_handlers(self, "scrub_failed")
    run_event_handlers(self, "scrub_finished")


  def handle_trim_started(self):
    succeed_request(self, RequestType.TRIM)

  def handle_trim_canceled(self):

    succeed_request(self, RequestType.CANCEL_TRIM)
    run_event_handlers(self, "trim_canceled")

  def handle_trim_finished(self):
    run_event_handlers(self, "trimmed")

  def enact_offline(self):
    return commands.add_script(f"zpool offline {self.pool} {self.dev_name()}", unless_redundant = True)

  def enact_online(self):
    return commands.add_script(f"zpool online {self.pool} {self.dev_name()}", unless_redundant = True)

  def enact_trim(self):
    return commands.add_script(f"zpool trim {self.pool} {self.dev_name()}", unless_redundant = True)

  def enact_scrub(self):
    self.stop_scrub()
    return commands.add_script(f"zpool scrub {self.pool}", unless_redundant = True)

  def stop_scrub(self):
    return commands.add_script(f"zpool scrub -s {self.pool}", unless_redundant = True)

  def enact_cancel_scrub(self):
    return self.stop_scrub()

  def enact_cancel_trim(self):
    return self.stop_trim()

  def stop_trim(self):
    return commands.add_script(f"zpool trim -s {self.pool} {self.dev_name()}", unless_redundant = True)

  def __kiify__(self, kd_stream: KdStream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operations", "last_online", "last_update", "last_scrub", "last_trim", "errors"])





NAME_FOR_TYPE = {
  None: None,
  Disk: "disk",
  Partition: "part",
  ZPool: "zpool",
  ZDev: "zdev",
  ZFSVolume: "zvol",
  DMCrypt: "crypt",
  ZMirror: "zmirror",
  UnavailableDependency: "unavailable-dependency",
  Mirror: "mirror"
}

TYPE_FOR_NAME = {value: key for key, value in NAME_FOR_TYPE.items()}
# legacy aliases for cache/config compatibility
TYPE_FOR_NAME["zfs-volume"] = ZFSVolume
TYPE_FOR_NAME["dm-crypt"] = DMCrypt
TYPE_FOR_NAME["partition"] = Partition
