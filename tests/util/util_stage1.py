
import inspect
import os

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

  def get_zpool_status_stub(args): #pylint: disable=unused-argument
          
          
    fn_name = get_caller_name_from_module(module_path)
    if fn_name is None:
       raise ValueError(f"this get_zpool_status_stub is only usable from within {module_path}")
    
    
    def rd(path):
      with open(path, "r", encoding="utf8") as file:
        return file.read()
      
    if relative_path is not None:
      path = f"{package_path}/{relative_path}"
      if not os.path.isfile(path):
        raise ValueError(f"could not resolve relative path {relative_path}")
      return rd(path)
    else:

      fn_z_path = f"{package_path}/res/{fn_name}.zpool-status.txt"
      if os.path.isfile(fn_z_path):
        return rd(fn_z_path)
      else:
        mod_z_path = f"{package_path}/res/zpool-status.txt"
        return rd(mod_z_path)




  import zmirror.entities as entities #pylint: disable=import-outside-toplevel
  entities.get_zpool_status = get_zpool_status_stub