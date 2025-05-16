import os

lvm_physical_volumes = dict()
zfs_blockdevs = dict()


cache_dict: dict = None
config_root = None
config_dict: dict = None
cache_path = None
config_path = None



def dev_exists(dev_path):
  if dev_path.startswith("/dev/"):
    return os.path.exists(dev_path)
  return os.path.exists("/dev/" + dev_path)


def get_zfs_volume_mode(zfs_path):
  raise NotImplementedError()

def is_zpool_backing_device_online(pool, dev):
  raise NotImplementedError()

def get_zpool_status(pool):
  raise NotImplementedError()

def load_config_for_id(args):
  raise NotImplementedError()