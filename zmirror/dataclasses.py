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
from .util import read_file
from enum import Enum


from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream, yes_no_absent_or_dict, KiSymbol



from .logging import log
from . import commands as commands
from . import config as config
from .config import iterate_content_tree3_depth_first
from .requests import *
import dateparser
import re

def human_readable_id(entity):
  r = entity_id_string(entity)
  if hasattr(entity, "info"):
    entity = uncached(cached(entity))
    v = entity.info
    if v is not None:
      return f"{r} ({v})"
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
  ONLINE = 1

  # present and offline (inactive)
  INACTIVE = 2


def state_corresponds_to_request(state, request):
  return state.value == request.value or (state == EntityState.INACTIVE and request in {RequestType.OFFLINE, RequestType.APPEAR}) or (state == EntityState.ONLINE and request == RequestType.APPEAR)

def operation_corresponds_to_request(oper, request):
  return oper.value == request.value




@yaml_enum
class Operation(KiEnum):
  RESILVER = 1
  SCRUB = 2
  TRIM = 3


def enum_command_name(enum):
  return enum.name.lower()


def is_online(entity):
  state = entity.get_state()
  return state == EntityState.ONLINE



def is_present_or_online(entity):
  state = entity.get_state()
  return state == EntityState.INACTIVE or state == EntityState.ONLINE



# returns the old state if the state changed if the state changed
def set_cache_state(o, st, since_unknown=False):
  if o.cache is not None:
    o = o.cache
  ost = o.state.what
  now = None
  if not since_unknown:
    now = inaccurate_now()
  if st == EntityState.INACTIVE or st == EntityState.DISCONNECTED:
    if o.state is not None and o.state.what == EntityState.ONLINE:
      o.last_online = now
      if hasattr(o, "operations") and Operation.RESILVER not in o.operations:
        o.last_update = now
  if ost != st:
    o.state = Since(st, now)
    return ost


property_name_for_operation = {
  Operation.RESILVER: "update",
  Operation.SCRUB: enum_command_name(Operation.SCRUB),
  Operation.TRIM: enum_command_name(Operation.TRIM)
}

def get_last_property_name_for_operation(op: Operation):
  return f"last_{property_name_for_operation[op]}"

request_for_zfs_operation = {
  Operation.RESILVER: RequestType.ONLINE,
  Operation.SCRUB: RequestType.SCRUB,
  Operation.TRIM: RequestType.TRIM
}

zfs_operation_for_request = {value: key for key, value in request_for_zfs_operation.items()}


@yaml_data
class ZMirror:
  log_events: bool = False
  enable_commands: bool = True
  timeout: int = 300
  log_level: str = "info"



  content: list = field(default_factory=list)
  notes: str = None


  update_interval: str = None
  scrub_interval: str = None
  trim_interval: str = None

  def id(self):
    return make_id(self)
  
  @classmethod
  def id_fields(cls):
    return []



def cached(entity):
  if entity.cache is None:
    tp, kwargs = entity.id()
    entity.cache = config.find_or_create_cache(tp, **kwargs)
  return entity.cache



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
  return TYPE_FOR_NAME(nm)



def make_id_string(x, **kwargs):
  if isinstance(x, tuple):
    return make_id_string(x[0], **x[1])
  elif not isinstance(x, type):
    raise ValueError("value must be type or tuple of type and arguments")
  return get_name_for_type(x) + "|" + '|'.join(f"{key}:{kwargs[key]}" for key in x.id_fields())

def entity_id_string(o):
  return make_id_string(o.id())




class Onlineable:

  def unsupported_request(self, request_type):
    if request_type in {RequestType.ONLINE, RequestType.OFFLINE}:
      return None
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE





class DependentNotFound(Exception):
  """Exception raised when a dependent is not found."""




def state_since_factory():
  return Since(EntityState.UNKNOWN, None)

@yaml_data
class Entity:

  parent = None
  cache = None
  requested: dict = field(default_factory=dict)
  state: Since = field(default_factory=state_since_factory, metadata={"db": True})
  last_online: datetime = field(metadata={"db": True}, default=None)
  notes: str = None


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


  def get_last_online(self):
    cache = cached(self)
    now = inaccurate_now()
    if cache.state.what is EntityState.ONLINE:
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
    if state == EntityState.ONLINE and request_type == RequestType.OFFLINE:
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

  def enact(self, request):

    request_type = request.request_type

    attr = f"enact_{request_type.name.lower()}"
    if hasattr(self, attr):
      def tell_request_enacted(cmd, returncode, _results, errors):
        if returncode != 0:
          request.fail(Reason.COMMAND_FAILED)
          log.error(f"command `{cmd.command}` failed: \n\t{"\n\t".join(errors)}")

      enact = getattr(self, attr)
      command = enact()
      command.on_execute.append(tell_request_enacted)
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


    if cache.state.what is not EntityState.ONLINE:
      kdstream.newline()
      kdstream.print_property(cache, "last_online", nil=KiSymbol("never"))

  def handle_onlined(self, prev_state):
    succeed_request(self, RequestType.ONLINE)
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
    return cached(self).state.what

  def handle_disconnected(self, prev_state):
    succeed_request(self, RequestType.OFFLINE)
    tell_parent_child_offline(self.parent, self, prev_state)



  def handle_deactivated(self, prev_state):
    succeed_request(self, RequestType.OFFLINE)
    tell_parent_child_offline(self.parent, self, prev_state)
    if isinstance(self.parent, Entity):
      if cached(self.parent).state.what == EntityState.DISCONNECTED:
        handle_disconnected(cached(self))




  def handle_parent_online(self, new_state=EntityState.INACTIVE):
    cache = cached(self)
    err_state = None
    if cache.state.what != EntityState.DISCONNECTED:
      err_state = cache.state.what
      if cache.state.what == EntityState.ONLINE:
        new_state = EntityState.ONLINE
    if err_state:
      log.error(f"{human_readable_id(self)} was already {err_state.name}, when parent became ONLINE. This is either some inconsistency in the cache (due to events being missed when zmirror wasn't running), or a bug in zmirror. Setting new state to: {new_state.name}. Please note, that this might not fix all inconsistencies, as now we will not run the event handlers for entity.on_appeared as it would be unsafe without knowledge of the previous state.")
    prev_state = set_cache_state(cache, new_state)
    if not err_state:
      if hasattr(self, "handle_appeared"):
        self.handle_appeared(prev_state)







  # must be overridden by child classes
  def get_dependencies(self, request):
    if request == RequestType.ONLINE:
      return [self.parent]
    return []





def run_actions(self, event_name, excepted=None):
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
  

  def handle_onlined(self, prev_state):
    super().handle_onlined(prev_state)
    for c in self.content:
      handle_parent_online(c)
  



  def handle_deactivated(self, prev_state):
    super().handle_deactivated(prev_state)
    for c in self.content:
      handle_parent_offline(c)



  def handle_disconnected(self, prev_state):
    super().handle_disconnected(prev_state)
    for c in self.content:
      handle_parent_offline(c)




  def handle_children_offline(self):
    self.enact_requests()
    run_actions(self, "children_offline")



#  def handle_child_online(self):
#    cached(self)
#    set_cache_state(self, EntityState.ONLINE)




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
          return commands.add_command(f"echo unmap > {path}")
        else:
          log.info(f"{human_readable_id(self)}: trim already enabled")




@yaml_data
class ManualChildren(Children):

  def unsupported_request(self, request_type):
    if request_type in {RequestType.ONLINE, RequestType.OFFLINE}:
      return Reason.MANUALLY_DISCONNECTED
    return Reason.NOT_SUPPORTED_FOR_ENTITY_TYPE



@yaml_data
class Disk(ManualChildren):


  uuid: str = None
  info: str = None

  force_enable_trim: bool = False

  @classmethod
  def id_fields(cls):
    return ["uuid"]




  def handle_appeared(self, prev_state):
    raise NotImplementedError(f"`{type(self).__name__}`s do not appear, they can only be ONLINE or DISCONNECTED")
  
  def handle_onlined(self, prev_state):
    possibly_force_enable_trim(self)
    return super().handle_onlined(prev_state)


  # this requires a udev rule to be installed which ensures that the disk appears under its GPT partition table UUID under /dev/disk/by-uuid
  def dev_path(self):
    return f"/dev/disk/by-uuid/{self.uuid}"

  def load_initial_state(self):
    return load_disk_or_partition_initial_state(self)

  def finalize_init(self):
    if cached(self).state.what in {EntityState.ONLINE, EntityState.INACTIVE}:
      possibly_force_enable_trim(self)


  def id(self):
    if self.uuid is not None:
      return make_id(self, uuid=self.uuid)
    else:
      raise ValueError("uuid not set")



@yaml_data
class Partition(ManualChildren):
  name: str = None





  @classmethod
  def id_fields(cls):
    return ["name"]



  def dev_path(self):
    return f"/dev/disk/by-partlabel/{self.name}"

  def load_initial_state(self):

    return load_disk_or_partition_initial_state(self)






  def id(self):
    return make_id(self, name=self.name)


def load_disk_or_partition_initial_state(self):
  # state = EntityState.DISCONNECTED
  if config.dev_exists(self.dev_path()):
    return EntityState.ONLINE
  return EntityState.DISCONNECTED
    #state = EntityState.INACTIVE
    # only the children being active can turn it into ONLINE
    #for c in self.content:
      # if cached(c).state.what == EntityState.ONLINE:
      #  state = EntityState.ONLINE
      #  break
  #return state



@yaml_data
class BackingDevice:
  device: Any
  required: bool = False
  online_dependencies: bool = True

  
  def unsupported_request(self, request_type):
    return self.device.unsupported_request(request_type)
  
  def state_supports(self, request_type):
    return self.device.state_supports(request_type)

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
      elif state == EntityState.ONLINE:
        one_online = True
      elif state == EntityState.DISCONNECTED or state == EntityState.UNKNOWN:
        if d.required:
          one_required_offline = True
    if one_required_offline:
      return EntityState.DISCONNECTED
    if one_required_inactive:
      return EntityState.INACTIVE
    if one_online:
      return EntityState.ONLINE
    if one_inactive:
      return EntityState.INACTIVE

@yaml_data
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
      elif state == EntityState.ONLINE:
        one_online = True
      elif state == EntityState.DISCONNECTED or state == EntityState.UNKNOWN:
        if hasattr(d, "required") and d.required:
          one_required_offline = True
    if one_required_offline:
      return EntityState.DISCONNECTED
    if one_required_inactive:
      return EntityState.INACTIVE
    if one_online:
      return EntityState.ONLINE
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


@yaml_data
class ZPool(Onlineable, Children):
  name: str = None

  backed_by: list = field(default_factory=list)

  on_backing_appeared: list = field(default_factory=list)

  _backed_by: list = None

  @classmethod
  def id_fields(cls):
    return ["name"]
  
  
  def state_allows(self, request_type):
    state = cached(self).state.what
    if state == EntityState.ONLINE and request_type == RequestType.OFFLINE:
      return True
    # a zpool is never INACTIVE, it is only ever DISCONNECTED, and whether
    # the state allows a request, depends solely on the request this 
    # request depends on (namely requests bringing zdevs online)
    elif state == EntityState.DISCONNECTED and request_type == RequestType.ONLINE:
      return True
    return False
  

  # def handle_appeared(self, prev_state):
  #  pass


  def request_dependencies(self, request_type, enactment_level: int = sys.maxsize):
    if request_type == RequestType.ONLINE:
      def do(backing):
        return backing.request(RequestType.APPEAR, enactment_level - 1)
      return list(map(do, self.backed_by))
    else:
      return super().request_dependencies(request_type, enactment_level= enactment_level)



  def print_status(self, kdstream):
    Entity.print_status(self, kdstream)

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
      run_actions(self, "backing_appeared")

  def handle_children_offline(self):
    return super().handle_children_offline()

  def handle_child_offline(self, child, prev_state):
    return super().handle_child_offline(child, prev_state)

  def handle_disconnected(self, prev_state):
    return super().handle_disconnected(prev_state)


  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    status = config.get_zpool_status(self.name)
    if status is not None:
      state = EntityState.ONLINE
    return state

  def finalize_init(self):
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
    return commands.add_command(f"zpool scrub {self.name}", unless_redundant = True)

  def stop_scrub(self):
    return commands.add_command(f"zpool scrub -s {self.name}", unless_redundant = True)



  def enact_offline(self):
    return commands.add_command(f"zpool export {self.name}", unless_redundant = True)

  def enact_online(self):
    if is_online(self):
      log.debug(f"zpool {self.name} already online")
      return

    sufficient = self.run_on_backing(is_present_or_online)
    if sufficient:
      log.info(f"{human_readable_id(self)}: sufficient backing devices available, importing zpool.")
      commands.add_command("udevadm settle")
      return commands.add_command(f"zpool import {self.name}", unless_redundant = True)
    else:
      log.info(f"{human_readable_id(self)}: insufficient backing devices available.")


  def run_on_backing(self, fn):
    sufficient = True
    for b in self._backed_by:
      if not fn(b):
        sufficient = False
    return sufficient




@yaml_data
class ZFSVolume(Children):
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
    if state == EntityState.ONLINE and request_type == RequestType.SNAPSHOT:
      return True
    return super().state_allows(request_type)

  def handle_appeared(self, prev_state):
    succeed_request(self, RequestType.APPEAR)
    self.enact_requests()
    run_actions(self, "appeared")

  def handle_children_offline(self):
    return super().handle_children_offline()

  def handle_parent_online(self, new_state=EntityState.INACTIVE):
    state = self.load_initial_state()
    if state == EntityState.INACTIVE:
      handle_appeared(cached(self))
    elif state == EntityState.ONLINE:
      handle_onlined(cached(self))
    else:
      log.error(f"{human_readable_id(self)}: inconsistent initial state ({state}). This is likely due to a misconfiguration.")


  def get_pool(self):
    if self.parent is not None:
      return self.parent.name
    else:
      return self.pool

  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    mode = config.get_zfs_volume_mode(f"{self.get_pool()}/{self.name}")
    if mode in {"full", "default"}:
      state = EntityState.ONLINE
    if mode == "none":
      state = EntityState.INACTIVE
    return state

  def enact_online(self):
    return commands.add_command(f"zfs set volmode=full {self.parent.name}/{self.name}")

  def enact_offline(self):
    return commands.add_command(f"zfs set volmode=none {self.parent.name}/{self.name}")

  def enact_snapshot(self):
    return commands.add_command(f"zfs snapshot {self.parent.name}/{self.name}@zmirror-{inaccurate_now().strftime("%Y-%m-%d_%H-%M-%S")}")


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
    if state == EntityState.ONLINE:
      log.info(f"{human_readable_id(self)}: parent OFFLINE, requesting OFFLINE.")
      request = self.request(RequestType.OFFLINE)
      request.enact_hierarchy()
    elif state == EntityState.INACTIVE:
      handle_disconnected(self)


@yaml_data
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


  def handle_appeared(self, prev_state):
    succeed_request(self, RequestType.APPEAR)
    self.enact_requests()
    run_actions(self, "appeared")


  def handle_child_online(self, child, prev_state):
    pass

  def load_initial_state(self):
    if config.dev_exists(self.dev_path()):
      return EntityState.ONLINE
    return EntityState.UNKNOWN

  def update_initial_state(self):
    if cached(self).state.what != EntityState.ONLINE:
      state = EntityState.DISCONNECTED
      if hasattr(self.parent, "state"):
        cp = cached(self.parent)
        if cp.state.what in [EntityState.INACTIVE, EntityState.ONLINE]:
          state = EntityState.INACTIVE
      return state


  def handle_children_offline(self):
    return super().handle_children_offline()

  def handle_child_offline(self, child, prev_state):
    return super().handle_child_offline(child, prev_state)

  def enact_offline(self):
    return commands.add_command(f"cryptsetup close {self.name}")

  def enact_online(self):
    return commands.add_command(f"cryptsetup open {self.parent.dev_path()} {self.name} --key-file {self.key_file}")


def uncached(cache, fn=None):
  if cache.cache is not None:
    entity = cache
  else:
    entity = config.load_config_for_cache(cache)
    if entity is None:
      log.debug(f"entity not configured: {entity_id_string(cache)}")
      return
    entity.cache = cache
  if fn:
    return fn(entity)
  else:
    return entity


def uncached_handle_by_name(cache, name, prev_state):
  def do(entity):
    method = getattr(entity, "handle_" + name)
    method(prev_state)
  uncached(cache, do)


def uncached_operation_handle_by_name(cache, name):
  def do(entity):
    method = getattr(entity, "handle_" + name)
    method()
  uncached(cache, do)


def uncached_userevent_by_name(cache, name):
  def do(entity):
    run_actions(entity, name)
  uncached(cache, do)

def inaccurate_now():
  return datetime.now().replace(microsecond=0)


def inaccurate_datetime(td):
  return td - timedelta(microseconds = td.microseconds)

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
  if not since_in(Operation.RESILVER, cache.operations):
    cache.operations.append(Since(Operation.RESILVER, inaccurate_now()))
    handle_onlined(cache)
    cache_log_info(cache, "resilver started")


# used for zdevs when brought online via zpool online (instead of zpool import)
def handle_zdev_onlined(cache):
  zdev = uncached(cache)
  if not zdev:
    log.debug(f"{human_readable_id(zdev)}: unconfigured, not assuming that it starts resilvering.")
    handle_onlined(cache)
  else:
    if zdev.is_mirror:
      handle_resilver_started(cache)
    else:
      handle_onlined(cache)


def handle_resilver_finished(cache):
  cache_log_info(cache, "resilvered (updated)")
  cache.last_update = inaccurate_now()
  since_remove(Operation.RESILVER, cache.operations)
  uncached_operation_handle_by_name(cache, "resilver_finished")


def handle_scrub_started(cache):
  cache_log_info(cache, "scrub started")
  since_insert_if_not_in(Since(Operation.SCRUB, inaccurate_now()), cache.operations)
  def do(entity):
    entity.handle_scrub_started()
  uncached(cache, do)


def handle_scrub_finished(cache):
  cache_log_info(cache, "scrubbed")
  now = inaccurate_now()
  since_remove(Operation.SCRUB, cache.operations)
  cache.last_scrub = now
  def do(entity):
    entity.handle_scrub_finished()
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
  prev_state = set_cache_state(cache, EntityState.DISCONNECTED)
  if prev_state is not None:
    cache_log_info(cache, "disconnected")
    uncached_handle_by_name(cache, "disconnected", prev_state)

# the device is still passively available
def handle_deactivated(cache):
  prev_state = set_cache_state(cache, EntityState.INACTIVE)
  if prev_state is not None:
    cache_log_info(cache, "deactivated")
    uncached_handle_by_name(cache, "deactivated", prev_state)

# the device became passively available
def handle_appeared(cache):
  prev_state = set_cache_state(cache, EntityState.INACTIVE)
  if prev_state is not None:
    cache_log_info(cache, "appeared")
    uncached_handle_by_name(cache, "appeared", prev_state)

# the device has activated
def handle_onlined(cache):
  prev_state = set_cache_state(cache, EntityState.ONLINE)
  if prev_state is not None:
    cache_log_info(cache, "onlined")
    uncached_handle_by_name(cache, "onlined", prev_state)





@yaml_data
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


@yaml_data
class ZDev(Onlineable, Embedded, Entity):
  pool: str = field(default=None)
  name: str = field(default=None)


  on_appeared: list = field(default_factory=list)

  operations: list = field(metadata={"db": True}, default_factory=list)

  last_online: datetime = field(metadata={"db": True}, default=None)
  last_update: datetime = field(metadata={"db": True}, default=None)
  last_scrub: datetime = field(metadata={"db": True}, default=None)
  last_trim: datetime = field(metadata={"db": True}, default=None)


  on_trimmed: list = field(default_factory=list)
  on_scrubbed: list = field(default_factory=list)
  on_scrub_canceled: list = field(default_factory=list)
  on_trim_canceled: list = field(default_factory=list)
  on_resilvered: list = field(default_factory=list)

  scrub_interval: str = None
  trim_interval: str = None
  update_interval: str = None

  is_mirror: bool = False

  @classmethod
  def id_fields(cls):
    return ["pool", "name"]
  

  def get_last_update(self):
    cache = cached(self)
    now = inaccurate_now()
    if cache.state.what == EntityState.ONLINE and Operation.RESILVER not in cache.operations:
      cache.last_update = now
      return KiSymbol("now")
    return cache.last_update
  

  def unsupported_request(self, request_type: RequestType):
    if request_type in [RequestType.OFFLINE, RequestType.ONLINE, RequestType.SCRUB, RequestType.TRIM]:
      return None
    return Embedded.unsupported_request(self, request_type)
  

  def state_allows(self, request_type: RequestType):
    cache = cached(self)
    if cache.state.what == EntityState.ONLINE:
      if request_type == RequestType.SCRUB:
        if not since_in(Operation.RESILVER, cache.operations):
          return True
      elif request_type == RequestType.TRIM:
        return True
    return super().state_allows(request_type)
    
  
  def finalize_init(self):
    for op in Operation:
      prop_name = f"{property_name_for_operation[op]}_interval"
      val = getattr(self, prop_name)
      if val is None:
        val = getattr(config.config_root, prop_name)
      if val is not None and val.lower() in {"nil", "none", "void"}:
        val = None
      setattr(self, prop_name, val)

  def effective_interval(self, op: Operation):
    return self.configured_interval(op)
  

  def configured_interval(self, op: Operation):
    return getattr(self, f"{property_name_for_operation[op]}_interval")
  
  def last(self, op: Operation):
    cache = cached(self)
    name = get_last_property_name_for_operation(op)
    return getattr(cache, name)

  
  def is_overdue(self, op: Operation):
    interval = self.effective_interval(op)
    if interval is not None:
      cache = cached(self)
      # parsing the schedule delta will result in a timestamp calculated from now
      allowed_delta = dateparser.parse(interval)
          # this means that allowed_delta is a timestamp in the past
      last = self.last(op)
      if last is None or allowed_delta > last:
        if op == Operation.RESILVER:
          if cache.state.what == EntityState.ONLINE and Operation.RESILVER not in cache.operations:
            return False
        if last is None:
          return inaccurate_datetime(allowed_delta - datetime.min)
        else:
          return inaccurate_datetime(allowed_delta - last)
    return False

  def handle_resilver_finished(self):

    run_actions(self, "resilvered")


  def print_status(self, kdstream):
    Entity.print_status(self, kdstream)
    cache = cached(self)
    
    
    for op in Operation:
      kdstream.newline()
      if op is Operation.RESILVER:
        kdstream.print_property_prefix("last_online")
        last_online = self.get_last_online()
        kdstream.print_obj(last_online, nil=KiSymbol("never"))
      else:
        kdstream.print_property(cache, get_last_property_name_for_operation(op), nil=KiSymbol("never"))
      if self.is_overdue(op):
        kdstream.print_raw(" # OVERDUE")
      kdstream.print_property(self, f"{property_name_for_operation[op]}_interval", hide_if_empty=True)

    if cache.operations:
      kdstream.newline()
      kdstream.print_property(cache, "operations")


  def is_fulfilled(self, request: Request):
    for op in self.operations:
      if operation_corresponds_to_request(op, request.request_type):
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
    if state != EntityState.ONLINE:
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

  def handle_appeared(self, prev_state):
    succeed_request(self, RequestType.APPEAR)
    pool_id = f"ZPool|name:{self.pool}"
    if pool_id in config.config_dict:
      config.config_dict[pool_id].handle_backing_device_appeared()
    run_actions(self, "appeared")

  def handle_scrub_started(self):
    succeed_request(self, RequestType.SCRUB)

  def handle_scrub_canceled(self):
    succeed_request(self, RequestType.CANCEL_SCRUB)
    run_actions(self, "scrub_canceled")

  def handle_scrub_finished(self):
    succeed_request(self, RequestType.SCRUB)
    run_actions(self, "scrubbed")


  def handle_trim_started(self):
    succeed_request(self, RequestType.TRIM)

  def handle_trim_canceled(self):

    succeed_request(self, RequestType.CANCEL_TRIM)
    run_actions(self, "trim_canceled")

  def handle_trim_finished(self):
    run_actions(self, "trimmed")

  def enact_offline(self):
    return commands.add_command(f"zpool offline {self.pool} {self.dev_name()}", unless_redundant = True)

  def enact_online(self):
    return commands.add_command(f"zpool online {self.pool} {self.dev_name()}", unless_redundant = True)

  def enact_trim(self):
    return commands.add_command(f"zpool trim {self.pool} {self.dev_name()}", unless_redundant = True)

  def enact_scrub(self):
    self.stop_scrub()
    return commands.add_command(f"zpool scrub {self.pool}", unless_redundant = True)

  def stop_scrub(self):
    return commands.add_command(f"zpool scrub -s {self.pool}", unless_redundant = True)

  def stop_trim(self):
    return commands.add_command(f"zpool trim -s {self.pool} {self.dev_name()}", unless_redundant = True)

  def __kiify__(self, kd_stream: KdStream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operations", "last_online", "last_update", "last_scrub", "last_trim"])





NAME_FOR_TYPE = {
  None: None,
  Disk: "disk",
  Partition: "partition",
  ZPool: "zpool",
  ZDev: "zdev",
  ZFSVolume: "zfs-volume",
  DMCrypt: "dm-crypt",
  ZMirror: "zmirror",
  UnavailableDependency: "unavailable-dependency",
  Mirror: "mirror"
}

TYPE_FOR_NAME = {value: key for key, value in NAME_FOR_TYPE.items()}