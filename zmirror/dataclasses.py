

from datetime import datetime
from dataclasses import dataclass, field


from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream

from .logging import log
# from zmirror_utils import set_entity_state, is_offline
# import zmirror_utils as core
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

@yaml_enum
class EntityState(KiEnum):
  # unknown state
  UNKNOWN = 0

  # offline and not present (inactive)
  DISCONNECTED = 1

  # present and online (active)
  ONLINE = 2
  
  # present and offline (inactive)
  INACTIVE = 3



def is_online(entity):
  return cached(entity).state.what == EntityState.ONLINE


def is_present_or_online(entity):
  c = cached(entity)
  return c.state.what == EntityState.INACTIVE or c.state.what == EntityState.ONLINE







# returns True if the state changed
def set_cache_state(o, st):
  if o.cache is not None:
    o = o.cache
  ost = o.state.what
  now = datetime.now()
  if st == EntityState.INACTIVE or st == EntityState.DISCONNECTED:
    if o.state is not None and o.state.what == EntityState.ONLINE:
      o.last_online = now
  o.state = Since(st, now)
  return ost != st





@yaml_enum
class ZFSOperationState(KiEnum):
  UNKNOWN = 0
  NONE = 1
  SCRUBBING = 2
  RESILVERING = 3




@yaml_data
class ZMirror:
  log_events: bool = False
  disable_commands: bool = False
  maintenance_schedule: str = None

  content: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None


def cached(entity):
  if entity.cache is None:
    tp, kwargs = entity.id()
    entity.cache = config.find_or_create_cache(tp, **kwargs) #pylint: disable=no-member
  return entity.cache


def make_id(o, **kwargs):
  return (type(o), kwargs)

def entity_id_string(o):
  tp, kwargs = o.id()
  return tp.__name__ + "|" + '|'.join(f"{key}:{value}" for key, value in kwargs.items())

@dataclass
class Entity:
  parent: object = None
  cache: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  notes: str = None


  def handle_disconnected(self):
    tell_parent_child_offline(self.parent)

  def handle_deactivated(self):
    tell_parent_child_offline(self.parent)


def run_actions(self, event_name):
  for event in getattr(self, "on_" + event_name): #pylint: disable=not-an-iterable
    if event == "offline":
      if hasattr(self, "take_offline"):
        self.take_offline()
      else:
        log.error(f"misconfiguration: entity {make_id(self)} does not support being taken offline manually")
    elif event == "online":
      if hasattr(self, "take_online"):
        self.take_online()
      else:
        log.error(f"misconfiguration: entity {make_id(self)} does not support being taken online manually")
    elif event == "snapshot":
      if hasattr(self, "take_snapshot"):
        self.take_snapshot()
      else:
        log.error(f"misconfiguration: entity {make_id(self)} does not have the ability to create snapshots")
    elif event == "scrub":
      if hasattr(self, "start_scrub"):
        self.start_scrub()
      else:
        log.error(f"misconfiguration: entity {make_id(self)} cannot be scrubbed")
    elif event == "trim":
      if hasattr(self, "do_trim"):
        self.do_trim()
      else:
        log.error(f"misconfiguration: entity {make_id(self)} cannot be trimmed")

    elif event == "snapshot-parent":
      if hasattr(self.parent, "take_snapshot"):
        self.parent.take_snapshot()
      else:
        log.error(f"misconfiguration: the parent entity of {make_id(self)} does not have the ability to create snapshots")
    else:
      log.error(f"unknown event type for {make_id(self)}.on_children_offline: {event}")


def tell_parent_child_offline(parent):
  if parent is not None:
    if hasattr(parent, "handle_child_offline"):
      parent.handle_child_offline()


def tell_parent_child_online(parent):
  if parent is not None:
    if hasattr(parent, "handle_child_online"):
      parent.handle_child_online()

@dataclass
class Children(Entity):
  content: list = field(default_factory=list) #pylint: disable=invalid-field-call

  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call



  def handle_onlined(self):
    for c in self.content: #pylint: disable=not-an-iterable
      if isinstance(c, ZFSBackingBlockDevice):
        handle_appeared(c)
    tell_parent_child_online(self.parent)


  def handle_children_offline(self):
    run_actions(self, "children_offline")


#  def handle_child_online(self):
#    cached(self)
#    set_cache_state(self, EntityState.ONLINE)


  def handle_child_offline(self):
    # if hasattr(self, "handle_children_offline"):
    online = False
    for c in self.content: #pylint: disable=not-an-iterable
      if is_online(c):
        online = True
    if not online:
      self.handle_children_offline()

  def handle_child_online(self):
    handle_onlined(self)


@yaml_data
class Partition(Children):
  name: str = None

  def get_devpath(self):
    return f"/dev/disk/by-partlabel/{self.name}"


  def handle_appeared(self):
    for c in self.content: #pylint: disable=not-an-iterable
      handle_appeared(c)

  def id(self):
    return make_id(self, name=self.name)



@yaml_data
class Disk(Entity):

  uuid: str = None

  # TODO: implement me
  force_enable_trim: bool = False

  def handle_appeared(self):
    pass


  content: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None

  def id(self):
    if self.uuid is not None:
      return make_id(self, uuid=self.uuid)
    else:
      raise ValueError("uuid not set")




@yaml_data
class MirrorBackingReference:
  devices: list = field(default_factory=list) #pylint: disable=invalid-field-call

@yaml_data
class ZPool(Children):
  name: str = None

  backed_by: list = field(default_factory=list) #pylint: disable=invalid-field-call


  on_backing_appeared: list = field(default_factory=list) #pylint: disable=invalid-field-call

  _backed_by: list = None

  def id(self):
    return make_id(self, name=self.name)
  
  def handle_onlined(self):
    for c in self.content: #pylint: disable=not-an-iterable
      # those are all `ZFSVolume`s
      handle_appeared(c)

  def handle_backing_device_appeared(self):
    run_actions(self, "backing_appeared")



  def start_scrub(self):
    commands.add_command(f"zpool scrub {self.name}")

  def take_offline(self):
    commands.add_command(f"zpool export {self.name}")

  def take_online(self):
    if is_online(self):
      log.debug(f"zpool {self.name} already online")
      return
    self.init_backing()
    sufficient = True
    for b in self._backed_by:
      one_present = False
      if isinstance(b, list):
        for x in b:
          if is_present_or_online(cached(x)):
            one_present = True
            break
      elif is_present_or_online(cached(b)):
        one_present = True
      if not one_present:
        sufficient = False
        break
    if sufficient:
      log.info(f"sufficient backing devices available to import zpool {self.name}")
      commands.add_command(f"zpool import {self.name}")
    else:
      log.info(f"insufficient backing devices available to import zpool {self.name}")
      



  def init_backing(self):


    if self._backed_by is None:
        self._backed_by = []
        if self.backed_by is not None and self.backed_by != []:
          blockdevs = config.zfs_blockdevs[self.name]

          def get_dev(name):
            dev = blockdevs[name]
            if dev is None:
              raise ValueError(f"misconfiguration: ZFSBackingBlockDevice for zpool {self.name} not configured: {name}")
            return dev
          if blockdevs is None:
            raise ValueError("misconfiguration: no `ZFSBackingBlockDevice`s configured for zpool {self.name}")
          for b in self.backed_by: #pylint: disable=not-an-iterable
            if isinstance(b, str):
              self._backed_by.append(get_dev(b))
            elif isinstance(b, MirrorBackingReference):
              mirror = []
              for x in b.devices:
                if isinstance(x, dict):
                  if not "required" in x:
                    raise ValueError(f"misconfiguration: backing for zpool {self.name}")
                  n = x["required"]
                  dev = get_dev(n)
                  self._backed_by.append(dev)
                  mirror.append(dev)
                elif isinstance(x, str):
                  dev = get_dev(x)
                  mirror.append(dev)
                else:
                  raise ValueError(f"misconfiguration: backing for zpool {self.name}")
              self._backed_by.append(mirror)

            else:
              raise ValueError(f"misconfiguration: unknown backing device type for zpool {self.name}")


@yaml_data
class ZFSVolume(Children):
  name: str = None
  pool: str = None


  on_appeared: list = field(default_factory=list) #pylint: disable=invalid-field-call

  def id(self):
    return make_id(self, pool=self.get_pool(), name=self.name)

  def handle_appeared(self):
    run_actions(self, "appeared")



  def get_pool(self):
    if self.parent is not None:
      return self.parent.name #pylint: disable=no-member
    else:
      return self.pool

  def take_online(self):
    commands.add_command(f"zfs set volmode=full {self.parent.name}/{self.name}")

  def take_offline(self):
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

  on_appeared: list = field(default_factory=list) #pylint: disable=invalid-field-call

  def id(self):
    return make_id(self, name=self.name)

  def get_devpath(self):
    return f"/dev/mapper/{self.name}"
  

  def handle_appeared(self):
    run_actions(self, "appeared")

  def handle_onlined(self):
    for c in self.content: #pylint: disable=not-an-iterable
      if isinstance(c, ZFSBackingBlockDevice):
        handle_appeared(c)
    tell_parent_child_online(self.parent)
  


  def take_offline(self):
    commands.add_command(f"cryptsetup close {self.name}")

  def take_online(self):
    commands.add_command(f"cryptsetup open {self.parent.get_devpath()} {self.name} --key-file {self.key_file}")


def uncached(cache, fn):
  if cache.cache is not None:
    entity = cache
  else:
    entity = config.load_config_for_cache(cache) #pylint: disable=no-member
    if entity is None:
      return
    entity.cache = cache
  fn(entity)


def uncached_handle_by_name(cache, name):
  def do(entity):
    method = getattr(entity, "handle_" + name)
    method()
  uncached(cache, do)


def uncached_userevent_by_name(cache, name):
  def do(entity):
    run_actions(entity, name)
  uncached(cache, do)


def handle_resilver_started(cache):
  cache.operation = Since(ZFSOperationState.RESILVERING, datetime.now())


def handle_resilver_finished(cache):
  cache.operation = Since(ZFSOperationState.NONE, datetime.now())
  uncached_userevent_by_name(cache, "resilvered")


def handle_scrub_started(cache):
  cache.operation = Since(ZFSOperationState.SCRUBBING, datetime.now())


def handle_scrub_finished(cache):
  now = datetime.now()
  cache.operation = Since(ZFSOperationState.NONE, now)
  cache.last_scrubbed = now
  uncached_userevent_by_name(cache, "scrubbed")


def handle_scrub_aborted(cache):
  cache.operation = Since(ZFSOperationState.NONE, datetime.now())
  uncached_userevent_by_name(cache, "scrub_aborted")



# the device or zpool has been taken offline and is not even passively available (it must be reactivated somehow)
def handle_disconnected(cache):
  if set_cache_state(cache, EntityState.DISCONNECTED):
    uncached_handle_by_name(cache, "disconnected")

# the device is still passively available
def handle_deactivated(cache):
  if set_cache_state(cache, EntityState.INACTIVE):
    uncached_handle_by_name(cache, "deactivated")

# the device became passively available
def handle_appeared(cache):
  if set_cache_state(cache, EntityState.INACTIVE):
    uncached_handle_by_name(cache, "appeared")


# the device has activated
def handle_onlined(cache):
  if set_cache_state(cache, EntityState.ONLINE):
    uncached_handle_by_name(cache, "onlined")


def activate(entity):
  c = cached(entity)
  set_cache_state(c, EntityState.ONLINE)


def deactivate(entity):
  c = cached(entity)
  set_cache_state(c, EntityState.INACTIVE)




@yaml_data
class ZFSBackingBlockDevice(Entity):
  pool: str = None
  dev: str = None

  on_appeared: list = field(default_factory=list) #pylint: disable=invalid-field-call

  operation = Since(ZFSOperationState.UNKNOWN, None)

  last_online: datetime = None
  last_scrubbed: datetime = None


  on_trimmed: list = field(default_factory=list) #pylint: disable=invalid-field-call
  on_scrubbed: list = field(default_factory=list) #pylint: disable=invalid-field-call
  on_scrub_aborted: list = field(default_factory=list) #pylint: disable=invalid-field-call
  on_resilvered: list = field(default_factory=list) #pylint: disable=invalid-field-call

  scrub_interval: str = None

  def id(self):
    return make_id(self, pool=self.pool, dev=self.dev_name())

  def dev_name(self):
    def do():
      if isinstance(self.parent, Partition):
        return self.parent.name
      elif isinstance(self.parent, DMCrypt):
        return self.parent.name
      elif isinstance(self.parent, ZFSVolume):
        return f"zvol/{self.parent.parent.name}/{self.parent.name}"
      else:
        return self.dev
    self.dev = do()
    return self.dev
  

  def handle_appeared(self):
    pool_id = f"ZPool|name:{self.pool}"
    if pool_id in config.config_dict: #pylint: disable=unsupported-membership-test
      config.config_dict[pool_id].handle_backing_device_appeared() #pylint: disable=unsubscriptable-object
    run_actions(self, "appeared")


  def handle_onlined(self):
    tell_parent_child_online(self.parent)



  def handle_scrub_finished(self):
    run_actions(self, "scrubbed")

  def handle_resilver_finished(self):
    run_actions(self, "resilvered")

  def handle_scrub_aborted(self):
    run_actions(self, "scrub_aborted")

  def take_offline(self):
    commands.add_command(f"zpool offline {self.pool} {self.dev_name()}")

  def take_online(self):
    commands.add_command(f"zpool online {self.pool} {self.dev_name()}")

  def start_trim(self):
    commands.add_command(f"zpool trim {self.pool} {self.dev_name()}")

  def start_scrub(self):
    commands.add_command(f"zpool scrub {self.pool}")

  def handle_resilvered(self):
    action = self.on_resilvered
    if action == "offline":
      self.take_offline()
    elif action == "scrub":
      self.start_scrub()

  def __kiify__(self, kd_stream: KdStream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operation", "last_resilvered", "last_scrubbed"])










"""
@yaml_data
class LVMLogicalVolume:
  name: str
  vg: str = None
  parent: object = None

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call
  content: list = field(default_factory=list)
  notes = str

  def get_devpath(self):
    if self.parent is not None:
      return f"/dev/{self.parent.name}/{self.name}"
    else:
      return f"/dev/{self.vg}/{self.name}"


  def id(self):
    if self.parent is not None:
      return f"{self.parent.name}|{self.name}"
    else:
      return f"{self.vg}|{self.name}"

  def take_offline(self):
    commands.add_command(f"lvchange --activate n {self.get_devpath()}")

  def take_online(self):
    commands.add_command(f"lvchange --activate y {self.get_devpath()}")



@yaml_data
class LVMPhysicalVolume:
  pv_uuid: str
  lvm_volume_group: str
  parent: object = None

  notes = str

  def id(self):
    return self.pv_uuid



@yaml_data
class LVMVolumeGroup:
  name: str

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call

  content: list = field(default_factory=list)
  notes = str

  def handle_offline(self):
    set_entity_state(self, EntityState.DISCONNECTED)
    for lvm_physical_volume in config.lvm_physical_volumes[self.name]:
      set_entity_state(lvm_physical_volume, EntityState.DISCONNECTED)


  def handle_child_online(self):
    if self.state.what is not EntityState.ONLINE:
      set_entity_state(self, EntityState.ONLINE)

  def handle_child_offline(self):
    at_least_one_child_online = False
    for children in self.content:
      if is_offline(children.state.what):
        at_least_one_child_online = True
    if not at_least_one_child_online:
      self.handle_offline()

      
@yaml_data
class VirtualDisk:

  fs_uuid: str
  devpath: str = None

  parent: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  content: list = field(default_factory=list)
  notes = str

  def id(self):
    return self.fs_uuid

  def get_devpath(self):
    return self.devpath
      

"""