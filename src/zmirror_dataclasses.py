from ki_utils import *

@yaml_data
class ZMirror:

  log_env: bool
  content = []

@yaml_data
class Partition:

  name: str
  content = []


  def get_hash(self):
    return hash((super().get_hash(), self.name))

@yaml_data
class Disk:

  serial: str

  content = []
  on_offline = None

  def get_hash(self):
    return hash((super().get_hash(), self.name))

@yaml_data
class ZPool:

  name: str
  on_offline: str = None
  content = []



@yaml_data
class Volume:

  name: str
  on_offline: str = None
  content = []


@yaml_data
class LVM_Volume_Group:

  name: str
  on_offline: str = None
  content = []

@yaml_data
class LVM_Logical_Volume:

  name: str
  on_offline: str = None
  content = []



@yaml_data
class LVM_Physical_Volume:

  lvm_volume_group: str
  on_offline: str = None


@yaml_enum
class DM_Crypt_State(Ki_Enum):
  UNKNOWN = 0
  DISCONNECTED = 1
  ONLINE = 2

@yaml_data
class DM_Crypt:

  name: str
  key_file: str

  state = DM_Crypt_State.UNKNOWN

  content = []

  on_offline: str = None

  def get_key(self):
    return self.__cls__.name + ":" + self.name



@yaml_data
class Since:
  what: object
  since: datetime

  def __to_kd__(self, kd_stream: Kd_Stream): 
    if self.since != None:
      kd_stream.stream.print_raw(self.__class__.__name__)
      kd_stream.stream.print_raw(" ")
      kd_stream.print_obj(self.since)
      kd_stream.stream.print_raw(" ")
    kd_stream.print_obj(self.what)

@yaml_enum
class ZFS_State(Ki_Enum):
  UNKNOWN = 0
  DISCONNECTED = 1
  ONLINE = 2

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

  state = Since(ZFS_State.UNKNOWN, None)
  operation = Since(ZFS_Operation_State.UNKNOWN, None)
  last_resilvered: datetime = None
  last_scrubbed: datetime = None

@yaml_data
class ZFS_Blockdev:
  pool: str
  dev: str
  on_scrubbed: str = None
  on_resilvered: str = None
  scrub_interval: str = None

@yaml_data
class ZFS_Blockdev_Output(ZFS_Blockdev, ZFS_Blockdev_Cache):
  def __to_kd__(self, kd_stream: Kd_Stream):
    kd_stream.print_partial_obj(self, ["pool", "dev", "state", "operation", "last_resilvered", "last_scrubbed"])