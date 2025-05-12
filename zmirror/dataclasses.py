

from datetime import datetime
from dataclasses import dataclass, field


from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream
from .logging import log
# from zmirror_utils import set_entity_state, is_offline
# import zmirror_utils as core
from . import commands as commands
from . import config as config



def set_entity_state(o, st):
  now = datetime.now()
  if st == EntityState.PRESENT or st == EntityState.DISCONNECTED:
    if o.state is not None and o.state.what == EntityState.ONLINE:
      o.last_online = now
  o.state = Since(st, now)

def is_offline(st):
  if st == EntityState.PRESENT or st == EntityState.DISCONNECTED:
    return True
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

  # OFFLINE and not present
  DISCONNECTED = 1

  # online and active
  ONLINE = 2
  
  # OFFLINE and present
  PRESENT = 3

@yaml_data
class ZMirror:
  log_events: bool = False
  disable_commands: bool = False
  maintenance_schedule: str = None

  content: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None


@yaml_data
class Partition:
  name: str
  state = Since(EntityState.UNKNOWN)
  devpath: str = None
  parent: object = None
  last_online: datetime = None
  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call
  content: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None

  def id(self):
    return self.name

  def handle_child_offline(self):
    set_entity_state(self, EntityState.PRESENT)

  def handle_child_online(self):
    set_entity_state(self, EntityState.ONLINE)



@yaml_data
class Disk:

  uuid: str = None

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  content: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None


  def id(self):
    if self.uuid is not None:
      return self.uuid
    else:
      raise ValueError("disk has no identifier")





@yaml_data
class ZPool:
  name: str

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call

  content: list = field(default_factory=list) #pylint: disable=invalid-field-call
  backed_by: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None

  def id(self):
    return self.name

  def take_offline(self):
    commands.add_command(f"zpool export {self.name}")

  def take_online(self):
    commands.add_command(f"zpool import {self.name}")


@yaml_data
class MirrorBackingReference:
  devices: list = field(default_factory=list) #pylint: disable=invalid-field-call
  notes: str = None

@yaml_data
class SimpleBackingReference:
  device: str
  notes: str = None

@yaml_data
class ZFSVolume:
  name: str
  pool: str = None
  parent: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call
  content: list = field(default_factory=list)  #pylint: disable=invalid-field-call
  notes: str = None

  def id(self):
    if self.parent is not None:
      return f"{self.parent.name}|{self.name}"
    else:
      return f"{self.pool}|{self.name}"

  def get_pool(self):
    if self.parent is not None:
      return self.parent.name
    else:
      return self.pool

      

  def get_devpath(self):
    if self.parent is not None:
      return f"/dev/zvol/{self.parent.name}/{self.name}"
    else:
      return f"/dev/zvol/{self.pool}/{self.name}"


@yaml_data
class DMCrypt:
  name: str
  key_file: str = None
  parent: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  on_children_offline: list = field(default_factory=list) #pylint: disable=invalid-field-call
  content = []
  notes: str = None

  def id(self):
    return self.name

  def get_devpath(self):
    return f"/dev/mapper/{self.name}"

  def take_offline(self):
    commands.add_command(f"cryptsetup close {self.name}")

  def take_online(self):
    commands.add_command(f"cryptsetup open {self.parent.get_devpath()} {self.name} --key-file {self.key_file}")


@yaml_enum
class ZFSOperationState(KiEnum):
  UNKNOWN = 0
  NONE = 1
  SCRUBBING = 2
  RESILVERING = 3


@yaml_data
class ZFSBackingBlockDeviceCache:
  pool: str
  dev: str

  state = Since(EntityState.UNKNOWN, None)
  operation = Since(ZFSOperationState.UNKNOWN, None)
  last_online: datetime = None
  last_resilvered: datetime = None
  last_scrubbed: datetime = None
  notes = str

  def id(self):
    return f"{self.pool}|{self.dev}"

@yaml_data
class ZFSBackingBlockDevice:
  pool: str
  # dev: str = None
  parent: object = None

  on_scrubbed: list = field(default_factory=list) #pylint: disable=invalid-field-call
  on_resilvered: list = field(default_factory=list) #pylint: disable=invalid-field-call
  on_parent_online: list = field(default_factory=list) #pylint: disable=invalid-field-call
  scrub_interval: str = None
  notes: str = None

  def id(self):
    return f"{self.pool}|{self.dev_name()}"

  def dev_name(self):
    if isinstance(self.parent, Partition):
      return self.parent.name
    elif isinstance(self.parent, DMCrypt):
      return self.parent.name
    elif isinstance(self.parent, ZFSVolume):
      return f"zvol/{self.parent.parent.name}/{self.parent.name}"


  def handle_scrubbed(self):
    action = self.on_scrubbed
    if action == "offline":
      self.take_offline()

  def handle_parent_online(self):
    log.error("NOT IMPLEMENTED")

  def take_offline(self):
    commands.add_command(f"zpool offline {self.pool} {self.dev_name()}")

  def take_online(self):
    commands.add_command(f"zpool online {self.pool} {self.dev_name()}")

  def start_scrub(self):
    commands.add_command(f"zpool scrub {self.pool}")

  def handle_resilvered(self):
    action = self.on_resilvered
    if action == "offline":
      self.take_offline()
    elif action == "scrub":
      self.start_scrub()






@yaml_data
class ZFSBackingBlockDeviceOutput(ZFSBackingBlockDevice, ZFSBackingBlockDeviceCache):
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