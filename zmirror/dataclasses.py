

from datetime import datetime
from dataclasses import dataclass, field


from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream


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
  # kwargs maintains insertion order, so this is reproducible!!!
  return tp.__name__ + "|" + '|'.join(f"{key}:{value}" for key, value in kwargs.items())

@dataclass
class Entity:
  parent = None
  cache = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  notes: str = None


  def handle_disconnected(self, prev_state):
    tell_parent_child_offline(self.parent, self, prev_state)

  def handle_deactivated(self, prev_state):
    tell_parent_child_offline(self.parent, self, prev_state)


  def handle_parent_onlined(self):
    cache = cached(self)
    new_state = EntityState.INACTIVE
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
  content: list = field(default_factory=list) #pylint: disable=invalid-field-call

  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call



  def handle_onlined(self, prev_state):
    for c in self.content: #pylint: disable=not-an-iterable
      if isinstance(c, ZFSBackingBlockDevice):
        c.handle_parent_onlined()
    tell_parent_child_online(self.parent, self, prev_state)
  
  
  def handle_deactivated(self, prev_state):
    super().handle_deactivated(prev_state)
    for c in self.content: #pylint: disable=not-an-iterable
      if isinstance(c, ZFSBackingBlockDevice):
        handle_disconnected(c)
  

  def handle_disconnected(self, prev_state):
    super().handle_deactivated(prev_state)
    for c in self.content: #pylint: disable=not-an-iterable
      if isinstance(c, ZFSBackingBlockDevice):
        handle_disconnected(c)



  def handle_children_offline(self):
    run_actions(self, "children_offline")


#  def handle_child_online(self):
#    cached(self)
#    set_cache_state(self, EntityState.ONLINE)


  def handle_child_offline(self, child, prev_state):
    
    # this change is irrelevant for the parent
    if prev_state == EntityState.INACTIVE:
      return
    # if hasattr(self, "handle_children_offline"):
    online = False
    for c in self.content: #pylint: disable=not-an-iterable
      if is_online(c):
        online = True
        break
    if not online:
      self.handle_children_offline()

  def handle_child_online(self, child, prev_state):
    set_cache_state(cached(self), EntityState.ONLINE)


@yaml_data
class Partition(Children):
  name: str = None

  def get_devpath(self):
    return f"/dev/disk/by-partlabel/{self.name}"

  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    if config.dev_exists(self.get_devpath()):
      state = EntityState.INACTIVE
      # only the children being active can turn it into ONLINE
      for c in self.content:
        if cached(c).state.what == EntityState.ONLINE:
          state = EntityState.ONLINE
          break
    set_cache_state(cached(self), state, True)

  def handle_appeared(self, prev_state):
    for c in self.content: #pylint: disable=not-an-iterable
      handle_appeared(cached(c))

  def id(self):
    return make_id(self, name=self.name)



@yaml_data
class Disk(Children):

  uuid: str = None

  # TODO: implement me
  force_enable_trim: bool = False

  def handle_appeared(self, prev_state):
    pass

  # this requires a udev rule to be installed which ensures that the disk appears under its GPT partition table UUID under /dev/disk/by-uuid
  def dev_path(self):
    return f"/dev/disk/by-uuid/{self.uuid}"

  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    if config.dev_exists(self.dev_path()):
      state = EntityState.INACTIVE
      # only the children being active can turn it into ONLINE
      for c in self.content:
        if cached(c).state.what == EntityState.ONLINE:
          state = EntityState.ONLINE
          break
    set_cache_state(cached(self), state, True)


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
  
  def handle_onlined(self, prev_state):
    for c in self.content: #pylint: disable=not-an-iterable
      # those are all `ZFSVolume`s
      c.load_initial_state()

  def handle_backing_device_appeared(self):
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
    
    set_cache_state(cached(self), state, True)



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
          if is_present_or_online(x):
            one_present = True
            break
      elif is_present_or_online(b):
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

  def handle_appeared(self, prev_state):
    run_actions(self, "appeared")

  def handle_children_offline(self):
    return super().handle_children_offline()

  def get_pool(self):
    if self.parent is not None:
      return self.parent.name #pylint: disable=no-member
    else:
      return self.pool
  

  def load_initial_state(self):
    state = EntityState.DISCONNECTED
    mode = config.get_zfs_volume_mode(f"{self.get_pool()}/{self.name}")
    if mode == "full":
      state = EntityState.ONLINE
    if mode == "none":
      state = EntityState.INACTIVE
    set_cache_state(cached(self), state, True)

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

  on_appeared: list = field(default_factory=list) #pylint: disable=invalid-field-call

  def id(self):
    return make_id(self, name=self.name)

  def get_devpath(self):
    return f"/dev/mapper/{self.name}"
  

  def handle_appeared(self, prev_state):
    run_actions(self, "appeared")

  def handle_onlined(self, prev_state):
    for c in self.content: #pylint: disable=not-an-iterable
      if isinstance(c, ZFSBackingBlockDevice):
        c.handle_parent_onlined()
    tell_parent_child_online(self.parent, self, prev_state)
  
  def handle_child_online(self, child, prev_state):
    pass

  def load_initial_state(self):
    if config.dev_exists(self.get_devpath()):
      set_cache_state(cached(self), EntityState.ONLINE, True)
        
  def update_initial_state(self):
    if cached(self).state.what != EntityState.ONLINE:
      state = EntityState.DISCONNECTED
      if hasattr(self.parent, "state"):
        if self.parent.state.what in [EntityState.INACTIVE, EntityState.ONLINE]:
          state = EntityState.INACTIVE
      set_cache_state(cached(self), state, True)



  def handle_children_offline(self):
    return super().handle_children_offline()
  
  def handle_child_offline(self, child, prev_state):
    return super().handle_child_offline(child, prev_state)

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
      log.warning(f"backing block device not configured: {entity_id_string(cache)}")
      return
    entity.cache = cache
  fn(entity)


def uncached_handle_by_name(cache, name, prev_state):
  def do(entity):
    method = getattr(entity, "handle_" + name)
    method(prev_state)
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
  prev_state = set_cache_state(cache, EntityState.DISCONNECTED)
  if prev_state:
    uncached_handle_by_name(cache, "disconnected", prev_state)

# the device is still passively available
def handle_deactivated(cache):
  prev_state = set_cache_state(cache, EntityState.INACTIVE)
  if prev_state:
    uncached_handle_by_name(cache, "deactivated", prev_state)

# the device became passively available
def handle_appeared(cache):
  prev_state = set_cache_state(cache, EntityState.INACTIVE)
  if prev_state:
    uncached_handle_by_name(cache, "appeared", prev_state)


# the device has activated
def handle_onlined(cache):
  prev_state = set_cache_state(cache, EntityState.ONLINE)
  if prev_state:
    uncached_handle_by_name(cache, "onlined", prev_state)




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
  

  

  def handle_appeared(self, prev_state):
    pool_id = f"ZPool|name:{self.pool}"
    if pool_id in config.config_dict: #pylint: disable=unsupported-membership-test
      config.config_dict[pool_id].handle_backing_device_appeared() #pylint: disable=unsubscriptable-object
    run_actions(self, "appeared")


  def handle_onlined(self, prev_state):
    tell_parent_child_online(self.parent, self, prev_state)


  def load_initial_state(self):
    state = EntityState.DISCONNECTED

    if config.is_zpool_backing_device_online(self.pool, self.dev_name()):
      state = EntityState.ONLINE
    else:
      dev = self.dev_name()
      if config.dev_exists(dev):
        state = EntityState.INACTIVE
    set_cache_state(cached(self), state, True)



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