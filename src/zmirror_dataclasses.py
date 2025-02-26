

from datetime import datetime
from ki_utils import yaml_data, yaml_enum, KiEnum, KdStream
import zmirror_commands
from zmirror_logging import log
# from zmirror_utils import set_entity_state, is_offline
# import zmirror_utils as core
import zmirror_globals as globals



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
    if when is None:
      when = datetime.now()
    self.when = when
    self.what = what

  def __to_kd__(self, kd_stream: KdStream):
    if self.when is not None:
      kd_stream.stream.print_raw(self.__class__.__name__)
      kd_stream.stream.print_raw(" ")
      kd_stream.print_obj(self.when)
      kd_stream.stream.print_raw(" ")
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
  log_env: bool
  content = []

@yaml_data
class Partition:
  name: str
  state = Since(EntityState.UNKNOWN)
  parent: object = None
  last_online: datetime = None
  on_children_offline: str = None
  content = []
  description = str

  def id(self):
    return self.name

  def on_child_offline(self):
    set_entity_state(self, EntityState.PRESENT)

  def on_child_online(self):
    set_entity_state(self, EntityState.ONLINE)



@yaml_data
class Disk:

  serial: str

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  content = []
  on_offline: str = None
  description = str


  def id(self):
    return self.serial


@yaml_data
class VirtualDisk:

  fs_uuid: str
  devpath: str

  parent: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  content = []
  on_offline: str = None
  description = str

  def id(self):
    return self.fs_uuid

  def get_devpath(self):
    return self.devpath



@yaml_data
class ZPool:
  name: str

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  on_offline: str = None
  content = []
  description = str

  def id(self):
    return self.name

  def take_offline(self):
    zmirror_commands.execute_command(f"zpool export {self.name}")

  def take_online(self):
    zmirror_commands.execute_command(f"zpool import {self.name}")



@yaml_data
class ZFSVolume:
  name: str
  parent: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  on_offline: str = None
  content = []
  description = str

  def id(self):
    return f"{self.parent.name}|{self.name}"

  def get_devpath(self):
    return f"/dev/zvol/{self.parent.name}/{self.name}"



@yaml_data
class LVMVolumeGroup:
  name: str

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  on_offline: str = None
  on_children_offline: str = None
  on_backing_offline: str = None
  content = []
  description = str

  def handle_offline(self):
    set_entity_state(self, EntityState.DISCONNECTED)
    for lvm_physical_volume in globals.lvm_physical_volumes[self.name]:
      set_entity_state(lvm_physical_volume, EntityState.DISCONNECTED)



  def handle_children_offline(self):
    if self.on_children_offline == "offline":
      self.take_offline()

  def on_child_offline(self):
    for child in self.content:
      if is_offline(child.state.what):
        self.handle_children_offline()

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
class LVMLogicalVolume:
  name: str
  vg: str = None
  parent: object = None

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  on_offline: str = None
  on_children_offline: str = None
  content = []
  description = str

  def id(self):
    return f"{self.parent.name}|{self.name}"

  def take_offline(self):
    zmirror_commands.execute_command(f"lvchange --activate n {self.parent.name}/{self.vg}")

  def take_online(self):
    zmirror_commands.execute_command(f"lvchange --activate y {self.parent.name}/{self.vg}")



@yaml_data
class LVMPhysicalVolume:
  pv_uuid: str
  lvm_volume_group: str
  parent: object = None

  on_offline: str = None
  description = str

  def id(self):
    return self.pv_uuid

  def on_group_offline(self):
    set_entity_state(self, EntityState.PRESENT)
    if self.parent is not None:
      self.parent.on_child_offline()
    else:
      log.error("Bug: parent is missing")

  def handle_parent_offline(self):
    if self.parent is not None and self.parent.state is not None:
      set_entity_state(self, self.parent.state.what)
    else:
      log.error("Bug: parent is missing or has no state")

@yaml_data
class DMCrypt:
  name: str
  key_file: str
  parent: object = None
  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None
  content = []
  on_offline: str = None
  description = str

  def id(self):
    return self.name

  def get_devpath(self):
    return f"/dev/mapper/{self.name}"

  def take_offline(self):
    zmirror_commands.execute_command(f"cryptsetup close {self.name}")

  def take_online(self):
    zmirror_commands.execute_command(f"cryptsetup open {self.parent.get_devpath()} {self.name} --key-file {self.key_file}")


@yaml_enum
class ZFSOperationState(KiEnum):
  UNKNOWN = 0
  NONE = 1
  SCRUBBING = 2
  RESILVERING = 3


@yaml_data
class ZFSBlockdevCache:
  pool: str
  dev: str

  state = Since(EntityState.UNKNOWN, None)
  operation = Since(ZFSOperationState.UNKNOWN, None)
  last_online: datetime = None
  last_resilvered: datetime = None
  last_scrubbed: datetime = None
  description = str

  def id(self):
    return f"{self.pool}|{self.dev}"

@yaml_data
class ZFSBlockdev:
  pool: str
  dev: str = None
  parent: object = None

  on_scrubbed: str = None
  on_resilvered: str = None
  on_offline: str = None
  scrub_interval: str = None

  def id(self):
    return f"{self.pool}|{self.dev}"

  def handle_scrubbed(self):
    action = self.on_scrubbed
    if action == "offline":
      self.take_offline()

  def handle_offline(self):
    action = self.on_offline
    if action == "offline-parent":
      if self.parent is not None and hasattr(self.parent, "take_offline"):
        self.parent.take_offline()

  def take_offline(self):
    zmirror_commands.execute_command(f"zpool offline {self.pool} {self.dev}")

  def take_online(self):
    zmirror_commands.execute_command(f"zpool online {self.pool} {self.dev}")

  def start_scrub(self):
    zmirror_commands.execute_command(f"zpool scrub {self.pool}")

  def handle_resilvered(self):
    action = self.on_resilvered
    if action == "offline":
      self.take_offline()
    elif action == "scrub":
      self.start_scrub()






@yaml_data
class ZFSBlockdevOutput(ZFSBlockdev, ZFSBlockdevCache):
  def __to_kd__(self, kd_stream: KdStream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operation", "last_resilvered", "last_scrubbed"])
