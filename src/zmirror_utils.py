from pyutils import *
from zmirror_dataclasses import *

def iterate_content_tree(o, fn):
  result = []
  fresult = fn(o)
  if fresult != None:
    result.append(o)
  if hasattr(o, "content"):
    lst = getattr(o, "content")
    if isinstance(lst, list):
      for e in lst:
        rlst = iterate_content_tree(e, fn)
        result = result + rlst
  return result

def find_or_create_zfs_cache_by_vdev_path(cache_dict, zpool, vdev_path):
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/")
  return find_or_create_cache(cache_dict, ZFS_Blockdev_Cache, pool=zpool, dev=vdev_name)

def get_zpool_status(zpool_name):
  returncode, zpool_status, formatted_response, formatted_error = exec(f"zpool status {zpool_name}")
  return zpool_status