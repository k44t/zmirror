

from datetime import datetime
from ki_utils import yaml_data, yaml_enum, KiEnum, KdStream
import zmirror_commands
from zmirror_logging import log

@yaml_data
class When:
  what: object
  since: datetime

  def __to_kd__(self, kd_stream: KdStream): 
    if self.since is not None:
      kd_stream.stream.print_raw(self.__class__.__name__)
      kd_stream.stream.print_raw(" ")
      kd_stream.print_obj(self.since)
      kd_stream.stream.print_raw(" ")
    kd_stream.print_obj(self.what)

@yaml_data
class Since(When):
  pass

@yaml_enum
class EntityState(KiEnum):
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
  state = Since(EntityState.UNKNOWN, None)
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




commands = []

def add_command(command):
  commands.append(command)


def execute_commands():
  seen = set()                                                    
  cmds = [x for x in commands if not (x in seen or seen.add(x))]

  for cmd in cmds:
    execute_command(cmd)

def execute_command(command):
  apply_commands = False
  if apply_commands:
    log.info(f"executing command: {command}")
    returncode, formatted_output, _, _ = exec(command)#pylint: disable=exec-used
    if returncode != 0:
      currently_scrubbing = False
      for line in formatted_output:
        if "currently scrubbing" in line:
          info_message = line
          log.info(info_message)
          currently_scrubbing = True
      if not currently_scrubbing:
        error_message = f"something went wrong while executing command {command}, terminating script now"
        log.error(error_message)
        exit(error_message)
    log.info(formatted_output)
  else:
    warning_message = f"applying command '{command}' is currently turned off!"
    log.warning(warning_message)

@yaml_data
class LVMVolumeGroup:
  name: str

  on_offline: str = None
  content = []
  description = str



@yaml_data
class LVMLogicalVolume:
  name: str
  vg: str = None
  parent: object = None

  state = Since(EntityState.UNKNOWN, None)
  last_online: datetime = None

  on_offline: str = None
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
  lvm_volume_group: str
  parent: object = None

  on_offline: str = None
  description = str




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
  dev: str
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




@yaml_data
class ZFSBlockdevOutput(ZFSBlockdev, ZFSBlockdevCache):
  def __to_kd__(self, kd_stream: KdStream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operation", "last_resilvered", "last_scrubbed"])
