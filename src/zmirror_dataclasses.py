from ki_utils import *
from zmirror_actions import *
import zmirror_utils as core


@yaml_data
class When:
  what: object
  since: datetime

  def __to_kd__(self, kd_stream: Kd_Stream): 
    if self.since != None:
      kd_stream.stream.print_raw(self.__class__.__name__)
      kd_stream.stream.print_raw(" ")
      kd_stream.print_obj(self.since)
      kd_stream.stream.print_raw(" ")
    kd_stream.print_obj(self.what)

@yaml_data
class Since(When):
  pass

@yaml_enum
class Entity_State(Ki_Enum):
  UNKNOWN = 0
  DISCONNECTED = 1
  ONLINE = 2

@yaml_data
class ZMirror:
  log_env: bool
  content = []

@yaml_data
class Partition:
  name: str
  state = Since(Entity_State.UNKNOWN, None)
  parent: object = None
  last_online: datetime = None
  content = []
  description = str

  def id(self):
    return self.name
  
  def handle_parent_online(self):
    raise NotImplementedError

@yaml_data
class Disk:
  
  serial: str
  
  state = Since(Entity_State.UNKNOWN, None)
  last_online: datetime = None
  
  content = []
  on_offline = None
  description = str


  def id(self):
    return self.serial


@yaml_data
class VirtualDisk:
  
  fs_uuid: str
  devpath: str
  
  parent: object = None
  state = Since(Entity_State.UNKNOWN, None)
  last_online: datetime = None
  
  content = []
  on_offline = None
  description = str

  def id(self):
    return self.fs_uuid

  def get_devpath(self):
    return self.devpath



@yaml_data
class ZPool:
  name: str

  state = Since(Entity_State.UNKNOWN, None)
  last_online: datetime

  on_offline: str = None
  content = []
  description = str

  def id(self):
    return self.name

  def take_offline(self):
    core.run_command(f"zpool export {self.name}")

  def take_online(self):
    core.run_command(f"zpool import {self.name}")



@yaml_data
class ZFS_Volume:
  name: str
  parent: object = None
  state = Since(Entity_State.UNKNOWN, None)
  last_online: datetime
  on_offline: str = None
  content = []
  description = str

  def id(self):
    return f"{self.parent.name}|{self.name}"

  def get_devpath(self):
    return f"/dev/zvol/{self.parent.name}/{self.name}"



@yaml_data
class LVM_Volume_Group:
  name: str
  
  on_offline: str = None
  content = []
  description = str



@yaml_data
class LVM_Logical_Volume:
  name: str
  vg: str = None
  parent: object = None
  
  state = Since(Entity_State.UNKNOWN, None)
  last_online: datetime = None
  
  on_offline: str = None
  content = []
  description = str

  def id(self):
    return f"{self.parent.name}|{self.name}"

  def take_offline(self):
    core.run_command(f"lvchange --activate n {self.parent.name}/{self.vg}")

  def take_online(self):
    core.run_command(f"lvchange --activate y {self.parent.name}/{self.vg}")


@yaml_data
class LVM_Physical_Volume:
  lvm_volume_group: str
  parent: object = None

  on_offline: str = None
  description = str
  



@yaml_data
class DM_Crypt:
  name: str
  parent: object = None
  key_file: str
  state = Since(Entity_State.UNKNOWN, None)
  last_online: datetime = None
  content = []
  on_offline: str = None
  description = str

  def id(self):
    return self.name

  def get_devpath(self):
    return f"/dev/mapper/{self.name}"

  def take_offline(self):
    core.run_command(f"cryptsetup close {self.name}")
    
  def take_online(self):
    core.run_command(f"cryptsetup open {self.parent.get_devpath()} {self.name} --key-file {self.key_file}")
    
  



@yaml_enum
class ZFS_Operation_State(Ki_Enum):
  UNKNOWN = 0
  NONE = 1
  SCRUBBING = 2
  RESILVERING = 3


@yaml_data
class ZFS_Blockdev_Cache:
  pool: str
  dev: str

  state = Since(Entity_State.UNKNOWN, None)
  operation = Since(ZFS_Operation_State.UNKNOWN, None)
  last_online: datetime = None
  last_resilvered: datetime = None
  last_scrubbed: datetime = None
  description = str

  def id(self):
    return f"{self.pool}|{self.dev}"

@yaml_data
class ZFS_Blockdev:
  pool: str
  dev: str
  parent: object = None

  on_scrubbed: str = None
  on_resilvered: str = None
  on_offline: str
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
      if self.parent != None and hasattr(self.parent, "take_offline"):
        self.parent.take_offline()
  
  def take_offline(self):
    core.run_command(f"zpool offline {self.pool} {self.dev}")
    
  def take_online(self):
    core.run_command(f"zpool online {self.pool} {self.dev}")




@yaml_data
class ZFS_Blockdev_Output(ZFS_Blockdev, ZFS_Blockdev_Cache):
  def __to_kd__(self, kd_stream: Kd_Stream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operation", "last_resilvered", "last_scrubbed"])