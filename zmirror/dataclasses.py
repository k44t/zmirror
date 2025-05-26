#!/bin/python


#pylint: disable=unsubscriptable-object
#pylint: disable=not-an-iterable
#pylint: disable=invalid-field-call
#pylint: disable=no-member
#pylint: disable=unsupported-membership-test


from datetime import datetime
from dataclasses import dataclass, field
import os
from typing import Any
from .util import read_file

import dateparser

from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream, yes_no_absent_or_dict



from .logging import log
from . import commands as commands
from . import config as config



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


@yaml_enum
class Request(KiEnum):

  OFFLINE = 0

  ONLINE = 1

  SCRUB = 2

  TRIM = 3

  def opposite(self):
    if self == Request.ONLINE:
      return Request.OFFLINE
    return Request.ONLINE


@yaml_enum
class ZFSOperationState(KiEnum):
  RESILVERING = 1
  SCRUBBING = 2
  TRIMMING = 3



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
    now = datetime.now()
  if st == EntityState.INACTIVE or st == EntityState.DISCONNECTED:
    if o.state is not None and o.state.what == EntityState.ONLINE:
      o.last_online = now
  if ost != st:
    o.state = Since(st, now)
    return ost






@yaml_data
class ZMirror:
  log_events: bool = False
  enable_commands: bool = True
  timeout: int = 300
  log_level: str = "info"


  content: list = field(default_factory=list)
  notes: str = None

  scrub_interval: str = None
  trim_interval: str = None



def cached(entity):
  if entity.cache is None:
    tp, kwargs = entity.id()
    entity.cache = config.find_or_create_cache(tp, **kwargs)
  return entity.cache



def make_id(o, **kwargs):
  if not isinstance(o, type):
    o = type(o)
  return (o, kwargs)

def make_id_string(x, **kwargs):
  if isinstance(x, tuple):
    return make_id_string(x[0], **x[1])
  elif not isinstance(x, type):
    raise ValueError("value must be type or tuple of type and arguments")
  return x.__name__ + "|" + '|'.join(f"{key}:{kwargs[key]}" for key in x.id_fields())

def entity_id_string(o):
  return make_id_string(o.id())




def state_corresponds_to_request(state, request):
  return id(state) == id(request) or (state == EntityState.INACTIVE and request == Request.OFFLINE)



class DependentNotFound(Exception):
    """Exception raised when a dependent is not found."""
    pass



def state_since_factory():
  return Since(EntityState.UNKNOWN, None)

def operation_since_factory():
  return Since(ZFSOperationState.UNKNOWN, None)

@yaml_data
class Entity:

  parent = None
  cache = None
  requested: set = field(default_factory=set)
  state: Since = field(default_factory=state_since_factory)
  last_online: datetime = None
  notes: str = None



  @classmethod
  def id_fields(cls):
    raise NotImplementedError()


  def print_status(self, kdstream):
    for prop in type(self).id_fields():
      kdstream.print_property(self, prop)
    kdstream.newline()

    cache = cached(self)
    kdstream.print_property(cache, "state")

    if self.requested:
      kdstream.print_property(self, "requested")


    if cache.state.what is not EntityState.ONLINE:
      kdstream.print_property(cache, "last_online")

  def handle_onlined(self, prev_state):
    self.unset_requested(Request.ONLINE)
    tell_parent_child_online(self.parent, self, prev_state)


  def id(self):
    raise NotImplementedError()

  def get_state(self):
    return cached(self).state.what

  def handle_disconnected(self, prev_state):
    self.unset_requested(Request.OFFLINE)
    tell_parent_child_offline(self.parent, self, prev_state)



  def handle_deactivated(self, prev_state):
    self.unset_requested(Request.OFFLINE)
    tell_parent_child_offline(self.parent, self, prev_state)



  def handle_parent_onlined(self, new_state=EntityState.INACTIVE):
    cache = cached(self)
    err_state = None
    if cache.state.what != EntityState.DISCONNECTED:
      err_state = cache.state
      if cache.state.what == EntityState.ONLINE:
        new_state = EntityState.ONLINE
    if err_state:
      log.error(f"{entity_id_string(self)} was already {err_state}, when parent became ONLINE. This is either some inconsistency in the cache (due to events being missed when zmirror wasn't running), or a bug in zmirror. Setting new state to: {new_state}. Please note, that this might not fix all inconsistencies, as now we will not run the event handlers for entity.on_appeared as it would be unsafe without knowledge of the previous state.")
    prev_state = set_cache_state(cache, new_state)
    if not err_state:
      self.handle_appeared(prev_state)



  def handle_appeared(self, prev_state):
    raise NotImplementedError()



  def set_requested(self, request, origin):
    online = is_online(self)
    if not ((request == Request.ONLINE and online) or (request == Request.OFFLINE and not online)):
      self.requested.add(request)
    return True

  def unset_requested(self, rqst):
    if rqst in self.requested:
      self.requested.remove(rqst)


  def request_locally(self, request, origin=None, all_dependencies=False):
    if request == Request.ONLINE:
      deps = self.get_dependencies(request)
      possible = True
      for dep in deps:
        if not is_online(dep):
          possible = False
      if possible:
        return self.request(request, origin, False, all_dependencies)
    elif request == Request.OFFLINE:
      if is_online(self):
        return self.request(request, origin, False, all_dependencies)




  def enact_request(self):



    cache = cached(self)

    state = cache.state.what

    for request in self.requested.copy():
      if state_corresponds_to_request(state, self.request):
        log.warning(f"{entity_id_string(self)}: request ({self.requested}) already fulfilled by state ({state}).")
        self.unset_requested(request)
      elif request == Request.ONLINE and state == EntityState.INACTIVE:
        self.unset_requested(Request.ONLINE)
        if hasattr(self, "take_online"):
          log.info(f"{entity_id_string(self)}: fullfilling request ({self.requested})")
          self.take_online()
        else:
          log.error(f"{entity_id_string(self)}: requested {self.requested}, but no take_online method. This is a bug in zmirror")
      elif request == Request.OFFLINE and state == EntityState.ONLINE:
        self.unset_requested(Request.OFFLINE)
        if hasattr(self, "take_offline"):
          log.info(f"{entity_id_string(self)}: fullfilling request ({self.requested})")
          self.take_offline()
        else:
          log.error(f"{entity_id_string(self)}: requested {self.requested}, but no take_offline method. This is a bug in zmirror")
      elif request == Request.SCRUB:
        if hasattr(self, "start_scrub"):
          if state == EntityState.ONLINE and not since_in(ZFSOperationState.RESILVERING, cache.operations):
            log.info(f"{entity_id_string(self)}: fullfilling request ({self.requested})")
            self.start_scrub()
          else:
            log.debug(f"{entity_id_string(self)}: currently cannot fulfill request ({self.requested}) because of state ({state})")
        else:
          log.error(f"{entity_id_string(self)}: requested {self.requested}, entity cannot be scrubbed.")
          self.unset_requested(Request.SCRUB)
      elif request == Request.TRIM:
        if hasattr(self, "start_trim"):
          if state == EntityState.ONLINE:
            log.info(f"{entity_id_string(self)}: fullfilling request ({self.requested})")
            self.start_trim()
          else:
            log.debug(f"{entity_id_string(self)}: currently cannot fulfill request ({self.requested}) because of state ({state})")
        else:
          log.error(f"{entity_id_string(self)}: requested {self.requested}, entity cannot be trimmed.")
          self.unset_requested(Request.TRIM)
      else:
          log.debug(f"{entity_id_string(self)}: currently cannot fulfill request ({self.requested}) because of state ({state})")





  # must be overridden by child classes
  def get_dependencies(self, request):
    if request == Request.ONLINE:
      return [self.parent]
    return []



  def request(self, request, origin=None, unrequest=False, all_dependencies=False):
    if unrequest:
      # yes origin is intended to not be == self here
      if request in self.requested:
        self.unset_requested(request)
        log.info(f"request {request} unrequested only for {entity_id_string(self)}")
        request_dependencies(self, origin, request, True, all_dependencies, self.get_dependencies(request))
        return True
      else:
        log.info(f"request {request} has not been requested and cannot be canceled")
        return False
    else:
      deps = self.get_dependencies(request)
      # yes origin is intended to not be == self here
      dependent_success = request_dependencies(self, origin, request, unrequest, all_dependencies, deps)
      if dependent_success:
        if self.set_requested(request, origin):
          if request == Request.OFFLINE:
            self.unset_requested(Request.SCRUB)
            self.unset_requested(Request.TRIM)
          return True
        else:
          # yes origin is intended to not be == self here
          request_dependencies(self, origin, request, True, all_dependencies, deps)
          log.error(f"failed to request {request} for {entity_id_string(self)}")
          return False
      else:
        return False



def request_dependencies(self, origin, request, unrequest, all_dependencies, deps):
  success = True
  for dep in deps:
    if not dep == origin:
      if hasattr(dep, "request"):
        if not dep.request(request, self, unrequest, all_dependencies):
          success = False
  return success



def run_actions(self, event_name, excepted=None):
  for event in getattr(self, "on_" + event_name):
    if event != excepted:
      run_action(self, event)



def run_action(self, event):
  if event == "offline":
    if hasattr(self, "take_offline"):
      if any(e in [Request.TRIM, Request.SCRUB] for e in self.requested):
        log.info(f"{entity_id_string(self)}: not taking offline since other operations are pending")
      else:
        self.take_offline()
    else:
      log.error(f"{entity_id_string(self)}: entity does not support being taken offline manually")
  elif event == "online":
    if hasattr(self, "take_online"):
      self.take_online()
    else:
      log.error(f"{entity_id_string(self)}: entity does not support being taken online manually")
  elif event == "snapshot":
    if hasattr(self, "take_snapshot"):
      self.take_snapshot()
    else:
      log.error(f"{entity_id_string(self)}: entity does not have the ability to create snapshots")
  elif event == "scrub":
    if hasattr(self, "start_scrub"):
      self.start_scrub()
    else:
      log.error(f"{entity_id_string(self)}: entity cannot be scrubbed")
  elif event == "trim":
    if hasattr(self, "start_trim"):
      self.start_trim()
    else:
      log.error(f"{entity_id_string(self)}: entity cannot be trimmed")

  elif event == "snapshot-parent":
    if hasattr(self.parent, "take_snapshot"):
      self.parent.take_snapshot()
    else:
      log.error(f"{make_id(self)}: the parent entity does not have the ability to create snapshots")
  elif event == "pass":
    # do nothing
    pass
  else:
    log.error(f"unknown event type for {make_id(self)}: {event}")



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



  def handle_onlined(self, prev_state):
    super().handle_onlined(prev_state)
    for c in self.content:
      if type(c) in {ZDev, ZFSVolume}:
        c.handle_parent_onlined()



  def handle_deactivated(self, prev_state):
    super().handle_deactivated(prev_state)
    for c in self.content:
      if isinstance(c, ZDev):
        handle_disconnected(c)



  def handle_disconnected(self, prev_state):
    super().handle_deactivated(prev_state)
    for c in self.content:
      if isinstance(c, ZDev):
        handle_disconnected(c)



  def get_dependencies(self, request):
    if request == Request.ONLINE:
      return [self.parent]
    elif request == Request.OFFLINE:
      return self.content
    else:
      return []



  def handle_children_offline(self):
    onlining = handle_offline_request(self)
    run_actions(self, "children_offline", "online" if onlining else None)



#  def handle_child_online(self):
#    cached(self)
#    set_cache_state(self, EntityState.ONLINE)




  def handle_child_offline(self, child, prev_state):

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

  def handle_child_online(self, child, prev_state):
    handle_onlined(cached(self))



def handle_offline_request(self):
  if Request.OFFLINE in self.requested:
    self.take_offline()
    return True
  return False



def handle_online_request(self):
  if Request.ONLINE in self.requested:
    self.take_online()
    return True
  return False



def possibly_force_enable_trim(self):
  if self.force_enable_trim:
    path = config.find_provisioning_mode(self.dev_path())
    if path is None:
      log.warning(f"{entity_id_string(self)}: failed to force enable trim, device (or provisioning_mode flag) not found.")
    else:
      state = read_file(path)
      if state != "unmap":
        log.warning(f"{entity_id_string(self)}: force enabling trim")
        commands.add_command(f"echo unmap > {path}")
      else:
        log.info(f"{entity_id_string(self)}: trim already enabled")


@yaml_data
class Disk(Children):

  uuid: str = None

  # TODO: implement me
  force_enable_trim: bool = False

  @classmethod
  def id_fields(cls):
    return ["uuid"]




  def handle_appeared(self, prev_state):
    possibly_force_enable_trim(self)

  def set_requested(self, request, origin):
    online = is_present_or_online(self)
    if (request == Request.ONLINE and online) or (request == Request.OFFLINE and not online):
      return True
    else:
      log.error(f"request {request} failed changing state ({request.opposite()}) of {entity_id_string(self)} is impossible. You need to manually bring the disk online.")
      return False

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
class Partition(Children):
  name: str = None





  @classmethod
  def id_fields(cls):
    return ["name"]



  def dev_path(self):
    return f"/dev/disk/by-partlabel/{self.name}"

  def load_initial_state(self):

    return load_disk_or_partition_initial_state(self)

  def handle_appeared(self, prev_state):
    for c in self.content:
      handle_appeared(cached(c))

  def set_requested(self, request, origin):
    if request == Request.ONLINE:
      if isinstance(self.parent, ZMirror):
        if not is_present_or_online(self):
          log.error(f"request ONLINE failed because {entity_id_string(self)} is not present and has no parent configured (which could be onlined).")
          return False
      return True
    else:
      return True


  def id(self):
    return make_id(self, name=self.name)


def load_disk_or_partition_initial_state(self):
    state = EntityState.DISCONNECTED
    if config.dev_exists(self.dev_path()):
      state = EntityState.INACTIVE
      # only the children being active can turn it into ONLINE
      for c in self.content:
        if cached(c).state.what == EntityState.ONLINE:
          state = EntityState.ONLINE
          break
    return state



@yaml_data
class BackingDevice:
  device: Any
  required: bool = False
  online_dependencies: bool = True



  def request(self, request, origin=None, unrequest=False, all_dependencies=False):
    return self.device.request(request, origin, unrequest, all_dependencies)

  def request_locally(self, request, origin=None, all_dependencies=False):
    return self.device.request_locally(request, origin, all_dependencies)

  def get_state(self):
    return self.device.get_state()


def unavailable_guard(blockdevs, devname):
  if devname in blockdevs:
    return blockdevs[devname]
  else:
    return UnavailableDependency(devname)

def init_backing(self, pool, blockdevs):
  self.parent = pool
  for i, dev in enumerate(self.devices):
    if isinstance(dev, str):
      self.devices[i] = BackingDevice(unavailable_guard(blockdevs, dev))
    else:
      if not "name" in dev:
        raise ValueError(f"misconfiguration: backing for {entity_id_string(pool)}. `name` missing in Mirror.")
      self.devices[i] = BackingDevice(
        unavailable_guard(blockdevs, dev["name"]),
        yes_no_absent_or_dict(dev, "required", False, f"misconfiguration: backing for {entity_id_string(pool)}"),
        yes_no_absent_or_dict(dev, "online_dependencies", True, f"misconfiguration: backing for {entity_id_string(pool)}")
      )


# Agregates are not entities but defer to entities

@yaml_data
class Agregate:
  pass


@yaml_data
class DevicesAgregate:

  devices: list = field(default_factory=list)

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

  pool = None

  def init(self, pool, blockdevs):
    init_backing(self, pool, blockdevs)

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


  def request(self, request, origin=None, unrequest=False, all_dependencies=False):
    one_failed = False
    one_succeeded = False
    for i, d in enumerate(self.devices):
      if request == Request.ONLINE:
        if all_dependencies or d.online_dependencies:
          res = d.request(request, origin, unrequest, all_dependencies)
        else:
          res = d.request_locally(request, origin, all_dependencies)
      else:
        res = d.request(request, origin, unrequest, all_dependencies)
      if res:
        one_succeeded = True
      else:
        if d.required:
          one_failed = True
          for d in self.devices[:i]:
            d.request(request, origin, True, all_dependencies)
          break
    return one_succeeded and not one_failed



@yaml_data
class ParityRaid(DevicesAgregate):
  parity: int = None
  parent = None


  def init(self, parent, blockdevs):
    init_backing(self, parent, blockdevs)




  def request(self, request, origin=None, unrequest=False, all_dependencies=False):
    one_failed = False
    num_succeeded = 0
    for d in self.devices:
      res = d.request(request, origin, unrequest, all_dependencies)
      if res:
        num_succeeded += 1
      else:
        if d.required:
          one_failed = True
    if one_failed or (num_succeeded < len(self.devices) - self.parity):
      for d in self.devices:
        d.request(request, origin, True, all_dependencies)
      return False
    return True





@yaml_data
class ZPool(Children):
  name: str = None

  backed_by: list = field(default_factory=list)

  on_backing_appeared: list = field(default_factory=list)

  _backed_by: list = None

  @classmethod
  def id_fields(cls):
    return ["name"]




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
      onlining = handle_online_request(self)
      run_actions(self, "backing_appeared", "online" if onlining else None)

  def handle_children_offline(self):
    return super().handle_children_offline()

  def handle_child_offline(self, child, prev_state):
    return super().handle_child_offline(child, prev_state)

  def handle_disconnected(self, prev_state):
    return super().handle_disconnected(prev_state)


  # must be overridden by child classes
  def get_dependencies(self, request):
    if request == Request.ONLINE:
      return self.backed_by
    elif request == Request.OFFLINE:
      return self.content
    else:
      return []


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
          backed[i] = UnavailableDependency(b)
      else:
        b.init(self, devs)




  def start_scrub(self):
    commands.add_command(f"zpool scrub -s {self.name}", unless_redundant = True)
    commands.add_command(f"zpool scrub {self.name}", unless_redundant = True)



  def take_offline(self):
      commands.add_command(f"zpool export {self.name}", unless_redundant = True)

  def take_online(self):
    if is_online(self):
      log.debug(f"zpool {self.name} already online")
      return

    sufficient = self.run_on_backing(is_present_or_online)
    if sufficient:
      log.info(f"sufficient backing devices available to import zpool {self.name}")
      commands.add_command(f"zpool import {self.name}", unless_redundant = True)
    else:
      log.info(f"insufficient backing devices available to import zpool {self.name}")


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


  def id(self):
    return make_id(self, pool=self.get_pool(), name=self.name)

  def handle_appeared(self, prev_state):
    onlining = handle_online_request(self)
    run_actions(self, "appeared", "online" if onlining else None)

  def handle_children_offline(self):
    return super().handle_children_offline()

  def handle_parent_onlined(self):
    state = self.load_initial_state()
    if state == EntityState.INACTIVE:
      handle_appeared(cached(self))
    elif state == EntityState.ONLINE:
      handle_onlined(cached(self))
    else:
      log.error(f"{entity_id_string(self)}: inconsistent initial state ({state}). this is a bug in zmirror.")


  def get_pool(self):
    if self.parent is not None:
      return self.parent.name
    else:
      return self.pool

  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    mode = config.get_zfs_volume_mode(f"{self.get_pool()}/{self.name}")
    if mode == "full":
      state = EntityState.ONLINE
    if mode == "none":
      state = EntityState.INACTIVE
    return state

  def take_online(self):
    #if self.cache.state.what == EntityState.INACTIVE:
      commands.add_command(f"zfs set volmode=full {self.parent.name}/{self.name}")

  def take_offline(self):
    #if self.cache.state.what == EntityState.ONLINE:
      commands.add_command(f"zfs set volmode=none {self.parent.name}/{self.name}")

  def take_snapshot(self):
    commands.add_command(f"zfs snapshot {self.parent.name}/{self.name}@zmirror-{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}")


  def get_devpath(self):
    if self.parent is not None:
      return f"/dev/zvol/{self.parent.name}/{self.name}"
    else:
      return f"/dev/zvol/{self.pool}/{self.name}"


@yaml_data
class DMCrypt(Children):
  name: str = None
  key_file: str = None

  @classmethod
  def id_fields(cls):
    return ["name"]

  on_appeared: list = field(default_factory=list)

  def id(self):
    return make_id(self, name=self.name)

  def get_devpath(self):
    return f"/dev/mapper/{self.name}"


  def handle_appeared(self, prev_state):
    onlining = handle_online_request(self)
    run_actions(self, "appeared", "online" if onlining else None)


  def handle_child_online(self, child, prev_state):
    pass

  def load_initial_state(self):
    if config.dev_exists(self.get_devpath()):
      return EntityState.ONLINE

  def update_initial_state(self):
    if cached(self).state.what != EntityState.ONLINE:
      state = EntityState.DISCONNECTED
      if hasattr(self.parent, "state"):
        if self.parent.state.what in [EntityState.INACTIVE, EntityState.ONLINE]:
          state = EntityState.INACTIVE
      return state



  def handle_children_offline(self):
    return super().handle_children_offline()

  def handle_child_offline(self, child, prev_state):
    return super().handle_child_offline(child, prev_state)

  def take_offline(self):
    commands.add_command(f"cryptsetup close {self.name}")

  def take_online(self):
    commands.add_command(f"cryptsetup open {self.parent.dev_path()} {self.name} --key-file {self.key_file}")


def uncached(cache, fn=None):
  if cache.cache is not None:
    entity = cache
  else:
    entity = config.load_config_for_cache(cache)
    if entity is None:
      log.warning(f"entity not configured: {entity_id_string(cache)}")
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


def handle_resilver_started(cache):
  if not since_in(ZFSOperationState.RESILVERING, cache.operations):
    log.info(f"{entity_id_string(cache)}: resilver started")
    cache.operations.append(Since(ZFSOperationState.RESILVERING, datetime.now()))


def handle_resilver_finished(cache):
  log.info(f"{entity_id_string(cache)}: resilvered")
  since_remove(ZFSOperationState.RESILVERING, cache.operations)
  uncached_operation_handle_by_name(cache, "resilver_finished")


def handle_scrub_started(cache):
  log.info(f"{entity_id_string(cache)}: scrub started")
  since_insert_if_not_in(Since(ZFSOperationState.SCRUBBING, datetime.now()), cache.operations)


def handle_scrub_finished(cache):
  log.info(f"{entity_id_string(cache)}: scrubbed")
  now = datetime.now()
  since_remove(ZFSOperationState.SCRUBBING, cache.operations)
  cache.last_scrubbed = now
  def do(entity):
    entity.handle_scrub_finished()
  uncached(cache, do)



def handle_trim_started(cache):
  log.info(f"{entity_id_string(cache)}: trim started")
  since_insert_if_not_in(Since(ZFSOperationState.TRIMMING, datetime.now()), cache.operations)


def handle_trim_finished(cache):
  log.info(f"{entity_id_string(cache)}: trimmed")
  now = datetime.now()
  since_remove(ZFSOperationState.TRIMMING, cache.operations)
  cache.last_trimmed = now
  def do(entity):
    entity.handle_trim_finished()
  uncached(cache, do)


def handle_scrub_canceled(cache):
  log.info(f"{entity_id_string(cache)}: scrub canceled")
  since_remove(ZFSOperationState.SCRUBBING, cache.operations)
  uncached_userevent_by_name(cache, "scrub_canceled")


def handle_trim_canceled(cache):
  log.info(f"{entity_id_string(cache)}: trim canceled")
  since_remove(ZFSOperationState.TRIMMING, cache.operations)
  uncached_userevent_by_name(cache, "trim_canceled")





# the device or zpool has been taken offline and is not even passively available (it must be reactivated somehow)
def handle_disconnected(cache):
  log.info(f"{entity_id_string(cache)}: disconnected")
  prev_state = set_cache_state(cache, EntityState.DISCONNECTED)
  if prev_state:
    uncached_handle_by_name(cache, "disconnected", prev_state)

# the device is still passively available
def handle_deactivated(cache):
  log.info(f"{entity_id_string(cache)}: deactivated")
  prev_state = set_cache_state(cache, EntityState.INACTIVE)
  if prev_state:
    uncached_handle_by_name(cache, "deactivated", prev_state)

# the device became passively available
def handle_appeared(cache):
  log.info(f"{entity_id_string(cache)}: appeared")
  prev_state = set_cache_state(cache, EntityState.INACTIVE)
  if prev_state:
    uncached_handle_by_name(cache, "appeared", prev_state)


# the device has activated
def handle_onlined(cache):
  log.info(f"{entity_id_string(cache)}: onlined")
  prev_state = set_cache_state(cache, EntityState.ONLINE)
  if prev_state:
    uncached_handle_by_name(cache, "onlined", prev_state)





@yaml_data
class UnavailableDependency:

  name: str

  def request(self, request, origin=None, unrequest=False, all_dependencies=False):
    return False


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




@yaml_data
class ZDev(Entity):
  pool: str = None
  name: str = None


  on_appeared: list = field(default_factory=list)

  # TODO: apparently scrub is impossible while resilvering, but trim is possible
  # now we need to check whether trim is possible while scrubbing, probably yes
  operations: list = field(default_factory=list)

  last_online: datetime = None
  last_scrubbed: datetime = None
  last_trimmed: datetime = None


  on_trimmed: list = field(default_factory=list)
  on_scrubbed: list = field(default_factory=list)
  on_scrub_canceled: list = field(default_factory=list)
  on_trim_canceled: list = field(default_factory=list)
  on_resilvered: list = field(default_factory=list)

  scrub_interval: str = None
  trim_interval: str = None

  @classmethod
  def id_fields(cls):
    return ["pool", "name"]

  def is_scrub_overdue(self):
    interval = self.scrub_interval or config.config_root.scrub_interval
    if interval is not None:
      cache = cached(self)
      # parsing the schedule delta will result in a timestamp calculated from now
      allowed_delta = dateparser.parse(interval)
          # this means that allowed_delta is a timestamp in the past
      return cache.last_scrubbed is None or allowed_delta > cache.last_scrubbed
    return False

  def is_trim_overdue(self):
    interval = self.trim_interval or config.config_root.trim_interval
    if interval is not None:
      cache = cached(self)
      # parsing the schedule delta will result in a timestamp calculated from now
      allowed_delta = dateparser.parse(interval)
          # this means that allowed_delta is a timestamp in the past
      return cache.last_trimmed is None or allowed_delta > cache.last_trimmed
    return False

  def print_status(self, kdstream):
    Entity.print_status(self, kdstream)
    cache = cached(self)
    if cache.operations:
      kdstream.newline()
      kdstream.print_property(cache, "operations")
    kdstream.newline()
    kdstream.print_property_prefix("last_scrubbed")
    kdstream.print_obj(cache.last_scrubbed)
    if self.is_scrub_overdue():
      kdstream.print_raw(" # OVERDUE")
    if self.scrub_interval:
      kdstream.print_property(self, "scrub_interval")
    if self.scrub_interval:
      kdstream.print_property(self, "trim_interval")
    kdstream.newline()
    kdstream.print_property(cache, "last_trimmed")



  def enact_request(self):
    cache = cached(self)
    if since_in(ZFSOperationState.TRIMMING, cache.operations) and Request.TRIM not in self.requested:
      self.stop_trim()
    elif since_in(ZFSOperationState.SCRUBBING, cache.operations) and Request.SCRUB not in self.requested:
      self.stop_scrub()
    return super().enact_request()


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



  # must be overridden by child classes
  def get_dependencies(self, request):
    if request == Request.ONLINE:
      pool = config.find_config(ZPool, name=self.pool)
      if pool is None:
        log.error(f"{entity_id_string(self)}: pool {self.pool} not configured.")
        pool = UnavailableDependency(entity_id_string(self))
      return [self.parent, pool]
    else:
      return []





  def set_requested(self, request, origin):
    success = True
    if request == Request.OFFLINE and Request.SCRUB in self.requested:
      log.warning(f"{entity_id_string(self)}: OFFLINE requested while SCRUB was requested. Unrequesting SCRUB.")
      if not self.request(Request.SCRUB, origin, True):
        success = False

    elif request == Request.SCRUB or request == Request.TRIM:
      if not self.request(Request.ONLINE, self, unrequest=False, all_dependencies=False):
        success = False
    if success:
      return super().set_requested(request, origin)
    else:
      return False



  def load_initial_state(self):
    state = EntityState.DISCONNECTED

    if config.is_zpool_backing_device_online(self.pool, self.dev_name()):
      state = EntityState.ONLINE
    else:
      dev = self.dev_name()
      if config.dev_exists(dev):
        state = EntityState.INACTIVE
    return state


  def handle_appeared(self, prev_state):
    pool_id = f"ZPool|name:{self.pool}"
    if pool_id in config.config_dict:
      config.config_dict[pool_id].handle_backing_device_appeared()
    onlining = handle_online_request(self)
    run_actions(self, "appeared", "online" if onlining else None)



  def handle_onlined(self, prev_state):
    super().handle_onlined(prev_state)
    if Request.SCRUB in self.requested:
      self.start_scrub()
    if Request.TRIM in self.requested:
      self.start_trim()



  def handle_resilver_finished(self):
    scrubbing = False
    if Request.SCRUB in self.requested:
      self.start_scrub()
      scrubbing = True
    run_actions(self, "resilvered", "scrub" if scrubbing else None)

  def handle_scrub_canceled(self):
    run_actions(self, "scrub_canceled")

  def handle_scrub_finished(self):

    self.unset_requested(Request.SCRUB)
    run_actions(self, "scrubbed")


  def handle_trim_canceled(self):
    run_actions(self, "trim_canceled")

  def handle_trim_finished(self):
    self.unset_requested(Request.TRIM)
    run_actions(self, "trimmed")


  def take_offline(self):
    commands.add_command(f"zpool offline {self.pool} {self.dev_name()}", unless_redundant = True)

  def take_online(self):
    commands.add_command(f"zpool online {self.pool} {self.dev_name()}", unless_redundant = True)

  def start_trim(self):
    commands.add_command(f"zpool trim {self.pool} {self.dev_name()}", unless_redundant = True)

  def start_scrub(self):
    self.stop_scrub()
    commands.add_command(f"zpool scrub {self.pool}", unless_redundant = True)

  def stop_scrub(self):
    commands.add_command(f"zpool scrub -s {self.pool}", unless_redundant = True)

  def stop_trim(self):
    commands.add_command(f"zpool trim -s {self.pool} {self.dev_name()}", unless_redundant = True)

  def __kiify__(self, kd_stream: KdStream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operations", "last_resilvered", "last_scrubbed"])

