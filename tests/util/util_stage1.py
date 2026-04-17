
import inspect
import os
import json
import re

def get_frame_data(levels=0):
  frame = inspect.currentframe()
  frame = frame.f_back
  for i in range(levels):
    frame = frame.f_back
  file = inspect.getfile(frame)
  return (os.path.dirname(file), file, frame.f_code.co_name)

def open_local(file, mode, levels=0):
  package_path, module_path, _ = get_frame_data(levels + 1)  #pylint: disable=unused-variable
  filepath = os.path.join(package_path, file)
  return open(filepath, mode, encoding="utf8")


def get_caller_name_from_module(module_path):
    stack = inspect.stack()
    for frame_info in stack:
        frame = frame_info.frame
        file_path = inspect.getfile(frame)
        if module_path in file_path:
            return frame.f_code.co_name #pylint: disable=protected-access
    return None


  
# must be called before the other zmirror modules are being imported. All the status loaded will be relative to the module that calls this function
def insert_zpool_status_stub(relative_path=None):

  package_path, module_path, _ = get_frame_data(1)  #pylint: disable=unused-variable

  def get_zpool_status_stub(zpool): #pylint: disable=unused-argument
          
          
    fn_name = get_caller_name_from_module(module_path)
    if fn_name is None:
       raise ValueError(f"this get_zpool_status_stub is only usable from within {module_path}")
    
    
    def rd(path):
      with open(path, "r", encoding="utf8") as file:
        r = file.read()
        if r == "":
          return None
        if path.endswith(".json"):
          return json.loads(r)
        return legacy_zpool_status_to_json(zpool, r)

      
    if relative_path is not None:
      path = f"{package_path}/{relative_path}"
      if not os.path.isfile(path):
        raise ValueError(f"could not resolve relative path {relative_path}")
    else:

      path = f"{package_path}/res/{fn_name}.zpool-status.txt"
      if os.path.isfile(path):
        return rd(path)
      else:
        path = f"{package_path}/res/{fn_name}.{zpool}.zpool-status.txt"
        if not os.path.isfile(path):
          path = f"{package_path}/res/{zpool}.zpool-status.txt"
          if not os.path.isfile(path):
            path = f"{package_path}/res/zpool-status.txt"
            if not os.path.isfile(path):
                raise ValueError(f"found no candidate for zpool-status.txt")
    return rd(path)




  import zmirror.config as config #pylint: disable=import-outside-toplevel
  config.get_zpool_status = get_zpool_status_stub


def legacy_zpool_status_to_json(zpool_name, text):
  scrub_errors = None
  match = re.search(r"with\s+([0-9]+)\s+errors", text)
  if match:
    scrub_errors = match.group(1)

  devices = {}
  in_config = False
  for line in text.splitlines():
    leading = len(line) - len(line.lstrip())
    stripped = line.strip()
    if stripped == "config:":
      in_config = True
      continue
    if not in_config:
      continue
    if stripped == "" or stripped.startswith("NAME "):
      continue
    if stripped.startswith("errors:"):
      break
    if leading < 4:
      continue

    parts = stripped.split()
    if len(parts) < 5:
      continue

    name = parts[0]
    state = parts[1]
    read_errors = parts[2]
    write_errors = parts[3]
    checksum_errors = parts[4]
    operations = []
    operations_match = re.search(r"\(([^)]*)\)\s*$", stripped)
    if operations_match:
      operations = [op.strip() for op in operations_match.group(1).split(",") if op.strip()]

    devices[name] = {
      "name": name,
      "state": state,
      "read_errors": read_errors,
      "write_errors": write_errors,
      "checksum_errors": checksum_errors,
      "operations": operations,
    }

  return {
    "output_version": {"command": "zpool status", "vers_major": 0, "vers_minor": 1},
    "pools": {
      zpool_name: {
        "name": zpool_name,
        "scan_stats": {"errors": scrub_errors if scrub_errors is not None else "0"},
        "vdevs": {
          zpool_name: {
            "name": zpool_name,
            "vdev_type": "root",
            "state": "ONLINE",
            "vdevs": devices,
          }
        },
      }
    },
  }



def find_in_file(path, line):

  with open(path, "r", encoding="utf8") as f:
    for l in f:
      if l == line:
        return True



def string_or_none_from_file(path):

  with open(path, "r", encoding="utf8") as f:
    r = f.read()
    if r == "":
      return None
    return r


def insert_dev_exists_stub():

  package_path, module_path, _ = get_frame_data(1)  #pylint: disable=unused-variable

  def dev_exists_stub(dev): #pylint: disable=unused-argument
          
          
    fn_name = get_caller_name_from_module(module_path)
    if fn_name is None:
       raise ValueError(f"this get_zpool_status_stub is only usable from within {module_path}")
    
    path = f"{package_path}/res/{fn_name}.devlinks.txt"
    
    if os.path.isfile(path):
      return find_in_file(path, dev)
    else:
      path = f"{package_path}/res/devlinks.txt"
      if os.path.isfile(path):
        return find_in_file(path, dev)
      else:
        raise ValueError("no corresponding devlinks.txt file found")
          
    return False
  
  import zmirror.config as config #pylint: disable=import-outside-toplevel
  config.dev_exists = dev_exists_stub



def insert_find_provisioning_mode_stub():
  package_path, module_path, _ = get_frame_data(1)  #pylint: disable=unused-variable

  def find_provisioning_mode_stub(zfs_path): #pylint: disable=unused-argument
    return f"{package_path}/res/provisioning_mode.txt"
  
  import zmirror.config as config #pylint: disable=import-outside-toplevel
  config.find_provisioning_mode = find_provisioning_mode_stub


def insert_get_zfs_volume_mode_stub():

  package_path, module_path, _ = get_frame_data(1)  #pylint: disable=unused-variable

  def zfs_volume_mode_stub(zfs_path): #pylint: disable=unused-argument
          
    zfs_path = zfs_path.replace("/", "_")
    fn_name = get_caller_name_from_module(module_path)
    if fn_name is None:
       raise ValueError(f"this get_zpool_status_stub is only usable from within {module_path}")
    
    path = f"{package_path}/res/{fn_name}.{zfs_path}.zfs_volume_mode.txt"
    
    if os.path.isfile(path):
      return string_or_none_from_file(path)
    else:
      path = f"{package_path}/res/{zfs_path}.zfs_volume_mode.txt"
      if os.path.isfile(path):
        return string_or_none_from_file(path)
      else:
        raise ValueError(f"no corresponding [{fn_name}.]{zfs_path}.zfs_volume_mode.txt file found")
          
    return False
  
  import zmirror.config as config #pylint: disable=import-outside-toplevel
  config.get_zfs_volume_mode = zfs_volume_mode_stub
