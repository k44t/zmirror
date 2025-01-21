



import numbers
import os, stat, os.path
import shutil
import re
import sys
import time
import subprocess
import yaml
from natsort import natsorted
from datetime import datetime, timedelta
import logging
import os
from enum import Enum
import argparse
import jsonpickle
import dateparser
import json
import traceback
from io import StringIO

from dataclasses import dataclass



class StringBuilder:
     _file_str = None

     def __init__(self):
         self._file_str = StringIO()

     def append(self, str):
         self._file_str.write(str)
         return self

     def __str__(self):
         return self._file_str.getvalue()

log = logging.getLogger(__name__)



# Create the parser
parser = argparse.ArgumentParser(description="zmirror worker")
subparser = parser.add_subparsers(required=True)
status_parser = subparser.add_parser('status', parents=[], help='show status of zmirror')


command_list = []

def convert_dict_to_strutex(dictionary):
  for key, value in dictionary.items():
    result_string = result_string + f"\n\t{key}:: {value}"
  return result_string




def ki_to_bool(v):
  if isinstance(v, bool):
    return v
  elif v == "yes":
    return True
  elif v == "no":
    return False
  else:
    raise BaseException("not a ki boolean")


def escape_ki_string(delim, string):
  index = 0
  l = len(string) - 1
  result = StringBuilder()
  fn = escape_ki_string_normal
  extra = ""
  while True:
    if index > l:
      if False and len(extra) > 0:
        if extra[0] == "\"":
          result.append("\\")
          result.append(extra)
        else:
          result.append(extra)
          result.append(extra[0])
      break
    fn, index, extra = fn(result, string, index, delim, extra)
  return str(result)

def escape_ki_string_backslash(result, string, index, delim, backslashes):
  if string[index] == "\\":
    return escape_ki_string_backslash,  index + 1, backslashes.append("\\")
  else:
    result.append("\\")
    result.append(str(backslashes))
    return escape_ki_string_normal,  index, StringBuilder()


def escape_ki_string_dollar(result, string, index, delim, dollars):
  if string[index] == "$":
    return escape_ki_string_dollar,  index + 1, dollars.append("$")
  else:
    result.append("\\")
    result.append(str(dollars))

    return escape_ki_string_normal, index, StringBuilder()
  
def escape_ki_string_delim(result, string, index, delim, quotes):
  if string[index] == delim:
    return escape_ki_string_delim, index + 1, quotes.append("\"")
  else:
    result.append("\\")
    result.append(str(quotes))

    return escape_ki_string_normal,   index, StringBuilder()


def escape_ki_string_normal(result, string, index, delim, ignoreme):
  # print("startresult: ", result)
  c = string[index]
  if c == "\\":
    return escape_ki_string_backslash,   index + 1, StringBuilder().append(c)
  elif c == "$":
    return escape_ki_string_dollar,  index + 1, StringBuilder().append(c)
  elif c == "\"":
    return escape_ki_string_delim, index + 1, StringBuilder().append(c)
  else:
    result.append(c)
    return escape_ki_string_normal, index + 1, StringBuilder()
    


#sys.stdout.write("escaped: '")
#sys.stdout.write(escape_ki_string('"', 'hello \\\\\\\\ $$$$ """" World!'))
#sys.stdout.write("'")
#exit()




class Ki_Enum(Enum):

  def __to_kd__(self, ki_stream):
    ki_stream.print("#" + self.name.lower().replace("_", "-"))


class Kd_Stream(): 
  def __init__(self, stream, indents = 0, level = -1):
    self.indents = indents
    self.stream = stream
    self.level = level


  def indent(self):
    self.indents = self.indents + 1

  def dedent(self):
    self.indents = self.indents - 1

  def newline(self):
    self.stream.write("\n")
    for i in range(0, self.indents):
        self.stream.write("  ")
  
  def print(self, string):
    self.stream.write(string)
        
  def print_obj(self, obj):
    if self.level == 0:
      self.stream.write("...")
      return
    self.level = self.level - 1
    if isinstance(obj, bool):
      if obj:
        self.stream.write("yes")
      else:
        self.stream.write("no")
    elif isinstance(obj, str):
      self.stream.write("\"")
      for i, line in enumerate(obj.split('\n')):
        if i > 0:
          self.newline()
        self.stream.write(escape_ki_string('"', line))
        # self.stream.write(line)
      self.stream.write("\"")
    elif isinstance(obj, numbers.Number):
      self.stream.write(str(obj))
    elif isinstance(obj, datetime):
      self.stream.write(obj.strftime("%Y-%m-%d'%H:%M:%S.%f"))
    elif isinstance(obj, list):
      self.stream.write("[:")
      self.indent()
      for i, element in enumerate(obj):
        # self.stream.write("||")
        self.newline()
        # self.stream.write(">>")
        self.print_obj(element)
        # self.stream.write("<<")
      self.dedent()
    elif isinstance(obj, dict):
      self.stream.write("{:")
      self.indent()
      for i, (key, value) in enumerate(obj.items()):
        self.newline()
        self.print_obj(key)
        self.stream.write(":")
        self.indent()
        self.print_obj(value)
        self.dedent()
      self.dedent()
    elif obj == None:
      self.stream.write("nil")
    elif hasattr(obj, "__to_kd__") and callable(obj.__to_kd__):
      obj.__to_kd__(self)
    else:
      self.print_python_obj(obj)

    self.level = self.level + 1

      
  def begin(self):
    self.stream.write('\n')
    self.stream.write(''.join([char*self.indents for char in " "]))
    
  def print_python_obj(self, obj):
    attrs = dir(obj)
    nattrs = []
    for attr in attrs:
      if not (attr.startswith("_") or callable(getattr(obj, attr))):
        nattrs.append(attr)
    self.print_partial_obj(obj, nattrs)

  def print_partial_obj(self, obj, props):
    if self.level == 0:
      self.stream.write("...")
      return
    self.stream.write(obj.__class__.__name__)
    self.indent()
    if len(props) > 0:
      for prop in props:
        if hasattr(obj, prop):
          # self.stream.write("..nl>")
          self.newline()
          # self.stream.write("..<nl")

          # self.stream.write("..>>")
          self.stream.write(prop)
          self.stream.write(": ")
          if callable(getattr(obj, prop)):
            self.stream.write("fn ...")
          else:
            # self.stream.write("|||")
            self.print_obj(getattr(obj, prop))
            # self.stream.write("<<..")
    else:
      self.stream.write("!")
    self.dedent()





def yaml_data(cls):                                                                                                                                                                                     
  # Perform operations using the class name                                                                                                                                                                      
  # print(f"Decorating class: {cls.__name__}")                                                                                                                                                                     
                                                                                                                                                                                                                    
  # You can add attributes or methods to the class if needed                                                                                                                                                     
  # cls.decorated = True                                                                                                                                                                                           

  def the_constr(loader, node):
    # https://github.com/yaml/pyyaml/blob/main/lib/yaml/constructor.py
    return loader.construct_yaml_object(node, cls)

  yaml.add_constructor(u"!" + cls.__name__, the_constr)


#  def the_repr(dumper, data):
  # https://github.com/yaml/pyyaml/blob/main/lib/yaml/representer.py
 #   return dumper.(node, cls)


  return dataclass(cls)
                                                                                                                                                                                                                    















@yaml_data
class ZMirror:
  
  log_env: bool
  content: list


@yaml_data
class Partition:

  name: str
  content: list
  
  
  def get_hash(self):
    return hash((super().get_hash(), self.name))


def my_constructor(loader, node):
  return loader.construct_yaml_object(node, Partition)



@yaml_data
class Disk:

  content: list
  on_offline: str
  serial: str

  def get_hash(self):
    return hash((super().get_hash(), self.name))


@yaml_data
class ZPool:

  name: str
  on_offline: str
  content: list



@yaml_data
class Volume:

  name: str
  on_offline: str
  content: list


@yaml_data
class LVM_Volume_Group:

  name: str
  on_offline: str
  content: list

@yaml_data
class LVM_Logical_Volume:

  name: str
  on_offline: str
  content: list



@yaml_data
class LVM_Physical_Volume:
  
  on_offline: str
  lvm_volume_group: str



@yaml_data
class DM_Crypt:

  name: str
  key_file: str
  scrubb_state: object
  dm_crypt_state: object

  content: dict "poolname|devname" -> obj
  
  on_offline: str
  
  def get_key(self):
    return self.__cls__.name + ":" + self.name

# objects from config
# objects from cache
# for o in config
#    if exists cache obj
#        take data from cache and copy to config


# {:
#   "DM_Crypt:eva-a-main": DM_Crypt
#     ohne content
#     ohne name
#     last-online: 2024...
#     

# event
#   which object is concerned?
# for event in config
#    
#    find event in cache
#    


action = None

def handle():
  if env.ZEVENT_CLASS != null:
    if env.ZEVENT_CLASS == "sys.zfs.Resilvered":
      pool = env.ZPOOL
      dev = env.ZDEV
      obj = find_config_and_cache_object(zmirror, ZFS, pool = pool, dev = dev)
      obj.resilvered = datetime.now()
      yaml.dump(zmirror)
  elif env.UDEV_ENV_VAR != None:
    if env.UDEV_ENV_VAR == "attach":
      if dev.TYPE == "Partition":
        name = env.PARTITION
        conf = find_config_object(zmirror, Partition, name = name)
        cache = find_cache_object(cache_dict, Partition, name = name)
        # nicht copy_to_cache(conf, cache)
        cache.attached = datetime.now()
        def offline_parent():
          exec("cryptsetup close {name}")
        action = offline_parent
  
  yaml.dump(cache_dict)
  action()



# zmirror trim-cache
        
def copy_to_cache(conf, cache)
  for prop in dir(conf):
    setattr(cache, prop, getattr(conf, prop))





class Scrubb_States(Ki_Enum):
  NOT_REQUESTED = 0
  PENDING = 1
  OVERDUE = 2


@yaml_data
class ZFS:
  
  pool: str
  dev: str
  name: str
  on_scrubbed: str
  on_resilvered: str
  current_operation: object
  state: object
  scrubb_state: object
  last_resilvered: str
  last_scrubbed: str
  scrub_interval: str




  
  def get_last_resilvered_string(self):
    if self.last_resilvered == None:
      return "Never"
    elif isinstance(self.last_resilvered, datetime):
      return self.last_resilvered.strftime("%Y-%m-%d %H:%M:%SZ")
    else:
      error_message = "last resilvered is no datetime. terminating script now."
      log.error(error_message)
      exit(error_message)
  def get_last_scrubbed_string(self):
    if self.last_scrubbed == None:
      return "Never"
    elif isinstance(self.last_scrubbed, datetime):
      return self.last_scrubbed.strftime("%Y-%m-%d %H:%M:%SZ")
    else:
      error_message = "last scrubbed is no datetime. terminating script now."
      log.error(error_message)
      exit(error_message)
  def get_hash(self):
    return hash((super().get_hash(), self.dev))






# yaml.dump(config)








class DM_Crypt_States(Ki_Enum):
  DISCONNECTED = -1
  ONLINE = 1

class DM_Crypt_State(object):
  def __init__(self, state = DM_Crypt_States.DISCONNECTED):
    if state.name not in DM_Crypt_States.__members__:
      log.error(f"Dm-Crypt-State `{state}` does not exist. Program will terminate.")
      exit()
    else:
      self.state = DM_Crypt_States(state)
  def get_state_name(self):
    if self.state == DM_Crypt_States.DISCONNECTED:
      return "disconnected"
    if self.state == DM_Crypt_States.ONLINE:
      return "online"

class Scrubb_States(Ki_Enum):
  NOT_REQUESTED = 0
  PENDING = 1
  OVERDUE = 2

@yaml_data
class Scrubb_State:

  state: object
  since: datetime

  def __init__(self, state = Scrubb_States.NOT_REQUESTED):
    if state.name not in Scrubb_States.__members__:
      log.error(f"Scrubb-State `{state}` does not exist. Program will terminate.")
      exit()
    else:
      self.state = Scrubb_States(state)
    self.since = datetime.now()
  def get_scrubb_state_string(self):
    since = self.since.strftime("%Y-%m-%d %H:%M:%SZ")
    if self.state == Scrubb_States.NOT_REQUESTED:
      return f"not-requested since: {since}"
    if self.state == Scrubb_States.PENDING:
      return f"pending since: {since}"
    if self.state == Scrubb_States.OVERDUE:
      return f"overdue since: {since}"


class ZFS_States(Ki_Enum):
  UNKNOWN = -2
  DISCONNECTED = -1
  PRESENT_BUT_OFFLINE = 0
  ONLINE = 1

class ZFS_State(object):
  def __init__(self, state = ZFS_States.DISCONNECTED):
    if state.name not in ZFS_States.__members__:
      log.error(f"ZFS_State `{state}` does not exist. Program will terminate.")
      exit()
    else:
      self.state = ZFS_States(state)
  def get_state_name(self):
    if self.state == ZFS_States.DISCONNECTED:
      return "disconnected"
    if self.state == ZFS_States.PRESENT_BUT_OFFLINE:
      return "present-but-offline"
    if self.state == ZFS_States.ONLINE:
      return "online"
    if self.state == ZFS_States.UNKNOWN:
      return "unknown"
  def get_state(self):
    return self.state

class ZFS_Operations(Ki_Enum):
  NONE = 0
  SCRUBBING = 1
  RESILVERING = 2

class ZFS_Operation(object):
  def __init__(self, state = ZFS_Operations.NONE):
    if state.name not in ZFS_Operations.__members__:
      log.error(f"active_operation `{state}` does not exist. Program will terminate.")
      exit()
    else:
      self.state = ZFS_Operations(state)
    self.start_time = datetime.now()
  def get_operation_string(self):
    start_time = self.start_time.strftime("%Y-%m-%d %H:%M:%SZ")
    if self.state == ZFS_Operations.NONE:
      return f"None: {start_time}"
    if self.state == ZFS_Operations.SCRUBBING:
      return f"scrubbing: {start_time}"
    if self.state == ZFS_Operations.RESILVERING:
      return f"resilvering: {start_time}"



# we are overriding python's internal exec, which would execute python code dynamically, because we don't need nor like it
def myexec(command):
    log.info(f"Executing command: {command}")
    process = subprocess.Popen(command,
                               shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    formatted_output = []
    formatted_response = []
    formatted_error = []
    # set blocking to not blocking is necessary so that readline wont block when the process already finished. this only works on linux systems!
    os.set_blocking(process.stdout.fileno(), False)
    os.set_blocking(process.stderr.fileno(), False)
    try:
        timestamp_last_stdout_readline_start = datetime.now()
        timestamp_last_stderr_readline_start = datetime.now()
        timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
        timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
        while process.poll() is None:
            if process.stdout != None:
                response_line = process.stdout.readline().decode("utf-8").replace("\n", "")
                if response_line != "":
                    log.info("stdout: " + response_line)
                if response_line != "":
                    timestamp_last_stdout_readline_start = datetime.now()
                    timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
                    timestamp_last_stderr_readline = datetime.now()
            if process.stderr != None:
                error_line = process.stderr.readline().decode("utf-8").replace("\n", "")
                if error_line != "":
                    log.error("stderr: " + error_line)
                if error_line != "":
                    timestamp_last_stderr_readline_start = datetime.now()
                    timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
                    timestamp_last_stdout_readline = datetime.now()
            if (process.stderr != None and error_line == "") and (process.stdout != None and response_line == ""):
                timestamp_stdout_now = datetime.now()
                timestamp_stderr_now = datetime.now()
                if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)) and \
                        timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
                    no_output_since = min(timestamp_stderr_now - timestamp_last_stderr_readline_start,
                                          timestamp_stdout_now - timestamp_last_stdout_readline_start)
                    log.warning(f"Command `{command}` had no stderr and stdout output since {no_output_since}.")
                    timestamp_last_stdout_readline = timestamp_stdout_now
                    timestamp_last_stderr_readline = timestamp_stderr_now
            elif (process.stderr != None and error_line == ""):
                timestamp_stderr_now = datetime.now()
                if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)):
                    log.warning(f"Command `{command}` had no stderr output since {timestamp_stderr_now - timestamp_last_stderr_readline_start}.")
                    timestamp_last_stderr_readline = timestamp_stderr_now
            elif (process.stdout != None and response_line == ""):
                timestamp_stdout_now = datetime.now()
                if timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
                    log.warning(f"Command `{command}` had no stdout output since {timestamp_stdout_now - timestamp_last_stdout_readline_start}.")
                    timestamp_last_stdout_readline = timestamp_stdout_now
            if response_line != "":
                formatted_response.append(response_line)
                formatted_output.append(response_line)
            if error_line != "":
                formatted_error.append(error_line)
                formatted_output.append(error_line)
    except Exception as e:
        pass
    try:
        response = process.stdout.readlines()
        for line in response:
            line = line.decode("utf-8").replace("\n", "")
            if line != "":
                log.info("stdout: " + line)
                formatted_response.append(line)
                formatted_output.append(line)
    except Exception as e:
        pass
    try:
        error = process.stderr.readlines()
        for line in error:
            line = line.decode("utf-8").replace("\n", "")
            if line != "":
                log.error("stderr: " + line)
                formatted_error.append(line)
                formatted_output.append(line)
    except Exception as e:
        pass
    return process.returncode, formatted_output, formatted_response, formatted_error
exec = myexec

def print_status(parent_object):
  try:
    parent_object.tag = parent_object.tag
  except Exception as e:
    return
  if parent_object.tag == "dm-crypt":
    dm_crypt_element = parent_object
    log_message = f"{dm_crypt_element.name} @{dm_crypt_element.tag}: {dm_crypt_element.scrubb_state.get_scrubb_state_string()}"
    log.info(log_message)
    print(log_message)
  if parent_object.tag == "zfs":
    zfs_element = parent_object
    log_message = f"""
    {zfs_element.dev} @ZFS: {zfs_element.state.get_state_name()}

    operation: {zfs_element.current_operation.get_operation_string()}

    last resilvered: '{zfs_element.get_last_resilvered_string()}'
    last scrubbed: '{zfs_element.get_last_scrubbed_string()}'

    scrub: {zfs_element.scrubb_state.get_scrubb_state_string()}
    """
    log.info(log_message)
    print(log_message)
  if isinstance(parent_object, Content_Element_with_Content_Elements):
    for object in parent_object.get_all_content_elements():
      print_status(object)

def show_status(args):
  zmirror_state = main()
  print_status(zmirror_state)


def get_current_zfs_state(zfs_object, zpool_status):
  global env_vars
  if "ZEVENT_CLASS" in env_vars:
    zevent_class = env_vars["ZEVENT_CLASS"]
    if zevent_class == "sysevent.fs.zfs.scrub_finish":
      regexp_pattern = rf'{zfs_object.name}\s+ONLINE\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$'
      regexp_searcher = re.compile(regexp_pattern)
      dev_status = regexp_searcher.search(zpool_status).groups()[0]
      if dev_status != "":
        return ZFS_State(ZFS_States.ONLINE)
      regexp_pattern = rf'{zfs_object.name}\s+OFFLINE\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$'
      regexp_searcher = re.compile(regexp_pattern)
      dev_status = regexp_searcher.search(zpool_status).groups()[0]
      if dev_status != "":
        return ZFS_State(ZFS_States.PRESENT_BUT_OFFLINE)
    if zevent_class == "resource.fs.zfs.statechange":
      if zevent_class["ZEVENT_VDEV_STATE_STR"] == "OFFLINE":
        return ZFS_State(ZFS_States.DISCONNECTED)
    if zevent_class == "sysevent.fs.zfs.vdev_online":
      return ZFS_State(ZFS_States.ONLINE)
  else:
    regexp_pattern = rf'.*{zfs_object.name}\s+ONLINE\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$'
    regexp_searcher = re.compile(regexp_pattern)
    results = list(filter(regexp_searcher.match, zpool_status))
    #for line in zpool_status:
    #  regexp_groups = regexp_searcher.match(line).groups()
    #dev_status = regexp_groups[0]
    if len(results) == 1:
      return ZFS_State(ZFS_States.ONLINE)
    else:
      return ZFS_State(ZFS_States.UNKNOWN)

'''
def read_list(yml_list):
  result = []
  for yml in yml_list:
    r = read_tag(yml)
    result.add(r)
  return result

def read_properties(yml, obj, props):
  for prop in props:
    if yaml_is_list(yml[prop]):
      v = read_list(yml[prop])
    else:
      v = yml[prop]
    setattr(obj, prop, v) 



def read_object(constructor):
  dict = read_properties(yml, obj, ["name", "key-file", "content"])
  python_run_function_with_dict(constructor, dict)

# und jetzt ist das ganze echt kompakt... und damit leicht zu warten. zwar immer noch if else, aber zusammengefasst, und weils python is etwa gleich schnell
def read_tag(yml):
  tag = yml.tag
  if tag == "dm-crypt":
    read_object(Dm_Crypt, yml, ["name", "key-file", "content"])
  elif tag == "zfs":
    read_object(ZFS, yml, ["..."])
  elif tag == "volume":
    read_object(Volume, yml, ["..."])
  elif tag == "zpool":
    read_object(ZPool, yml, ["..."])
  elif tag == "lvm-volume-group":
    read_object(Lvm_Volume_Group, yml, ["..."])
  elif tag == "lvm-volume":
    read_object(Lvm_Volume, yml, ["..."])
  elif tag == "disk":
    read_object(Disk, yml, ["..."])
  elif tag == "partition":
    read_object(Partition, yml, ["..."])
 
https://pyyaml.org/wiki/PyYAMLDocumentation

>>> class Monster(yaml.YAMLObject):
...     yaml_tag = u'!Monster'
...     def __init__(self, name, hp, ac, attacks):
...         self.name = name
...         self.hp = hp
...         self.ac = ac
...         self.attacks = attacks
...     def __repr__(self):
...         return "%s(name=%r, hp=%r, ac=%r, attacks=%r)" % (
...             self.__class__.__name__, self.name, self.hp, self.ac, self.attacks)

The above definition is enough to automatically load and dump Monster objects:

>>> yaml.load("""
... --- !Monster
... name: Cave spider
... hp: [2,6]    # 2d6
... ac: 16
... attacks: [BITE, HURT]
... """)

Monster(name='Cave spider', hp=[2, 6], ac=16, attacks=['BITE', 'HURT'])

>>> print yaml.dump(Monster(
...     name='Cave lizard', hp=[3,6], ac=16, attacks=['BITE','HURT']))


'''




def get_config_object(tag, parent_object, cache_object = None, config_entry_object = None, content_element = None, content_tag = None):
  

  result_object = None
  result_content = None
  if tag == "dm-crypt":
    dm_crypt = parent_object[tag]
    dm_crypt_name = dm_crypt["name"]
    dm_crypt_key_file = dm_crypt["key-file"]
    dm_crypt_content = dm_crypt["content"]
    dm_crypt_object = None
    # config_entry_object is either a disk or a partition:
    config_entry_object_content_elements = cache_object.get_all_content_elements()
    for config_entry_object_content_element in config_entry_object_content_elements:
      if config_entry_object_content_element.tag == tag:
        if config_entry_object_content_element.name == dm_crypt_name:
          if config_entry_object_content_element.key_file == dm_crypt_key_file:
            dm_crypt_object = config_entry_object_content_element
            break
    if dm_crypt_object == None:
      dm_crypt_object = Dm_Crypt(dm_crypt_name, dm_crypt_key_file)
    if ("DEVTYPE" in env_vars) \
      and ( \
        ( \
          env_vars["DEVTYPE"] == "disk" \
          and (("ID_SERIAL" in env_vars and env_vars["ID_SERIAL"] == config_entry_object.serial) \
          or ("DM_NAME" in env_vars and config_entry_object.name in env_vars["DM_NAME"])) \
        ) \
        or ( \
          env_vars["DEVTYPE"] == "partition" \
          and env_vars["PARTNAME"] == config_entry_object.name
        ) \
      ): #alexTODO: prüfen ob das mit dem partname eh so passt mit config_entry_object.name
        if env_vars["ACTION"] == "add":
          dm_crypt_object.dm_crypt_state.state = Dm_Crypt_States.ONLINE
        if env_vars["ACTION"] == "remove":
          dm_crypt_object.dm_crypt_state.state = Dm_Crypt_States.DISCONNECTED
    result_object = dm_crypt_object
    result_content = dm_crypt_content
  elif (tag in ["volume", "zpool", "lvm-volume-group", "lvm-volume"]):
    on_offline_element = parent_object[tag]
    on_offline_element_name = on_offline_element["name"]
    on_offline_element_on_offline = on_offline_element["on-offline"]
    on_offline_element_content = None
    if "content" in on_offline_element:
      on_offline_element_content = on_offline_element["content"]
    on_offline_element_object = None
    object_content_elements = cache_object.get_all_content_elements()
    for object_content_element in object_content_elements:
      if object_content_element.tag == content_tag:
        if object_content_element.name == on_offline_element_name:
          if object_content_element.on_offline == on_offline_element_on_offline:
            on_offline_element_object = object_content_element
            break
    if on_offline_element_object == None :
      if tag == "volume":
        on_offline_element_object = Volume(on_offline_element_name, on_offline_element_on_offline)
      elif  tag == "zpool":
        on_offline_element_object = ZPool(on_offline_element_name, on_offline_element_on_offline)
      elif  tag == "lvm-volume-group":
        on_offline_element_object = Lvm_Volume_Group(on_offline_element_name, on_offline_element_on_offline)
      elif  tag == "lvm-volume":
        on_offline_element_object = Lvm_Volume(on_offline_element_name, on_offline_element_on_offline)
    result_object = on_offline_element_object
    result_content = on_offline_element_content

  elif (tag == "disk"):
    disk = parent_object[tag]
    disk_serial = disk["serial"]
    config_entry_content = disk["content"]
    config_entry_object = None
    zmirror_content_elements = cache_object.get_all_content_elements()
    for zmirror_content_element in zmirror_content_elements:
      if zmirror_content_element.tag == content_tag:
        zmirror_disk_object = zmirror_content_element
        if zmirror_disk_object.name == disk_serial:
          config_entry_object = zmirror_disk_object
          break
    if config_entry_object == None:
      config_entry_object = Disk(disk_serial)
    result_object = config_entry_object
    result_content = config_entry_content
  elif (tag == "partition"):
    partition = parent_object[tag]
    partition_name = partition["name"]
    partition_content = partition["content"]
    partition_object = None
    partition_content_elements = cache_object.get_all_content_elements()
    for partition_content_element in partition_content_elements:
      if partition_content_element.tag == tag:
        partition_content_object = partition_content_element
        if partition_content_object.name == partition_name:
          partition_object = partition_content_object
          break
    if partition_object == None:
      # for some weird reason we need to give an empty list as content_elements, as otherwise content_elements will falsely be containing something in the second round (eva-b-main contained eva-a-main in content_elements even if this should have been an empty list then)
      partition_object = Partition(partition_name)
    result_object = partition_object
    result_content = partition_content
  elif (tag == "zfs"):
    zfs = parent_object[tag]
    zfs_pool = zfs["pool"]
    zfs_dev = zfs["dev"]
    zfs_on_scrubbed = None
    if "on-scrubbed" in zfs:
      zfs_on_scrubbed = zfs["on-scrubbed"]
    zfs_on_resilvered = None
    if "on-resilvered" in zfs:
      zfs_on_resilvered = zfs["on-resilvered"]
    zfs_scrub_interval = None
    if "scrub-interval" in zfs:
      zfs_scrub_interval = zfs["scrub-interval"]
    zfs_object = None
    lvm_volume_object_content_elements = cache_object.get_all_content_elements()
    for lvm_volume_object_content_element in lvm_volume_object_content_elements:
      if lvm_volume_object_content_element.pool == zfs_pool:
        if lvm_volume_object_content_element.dev == zfs_dev:
          if lvm_volume_object_content_element.on_scrubbed == zfs_on_scrubbed:
            if lvm_volume_object_content_element.on_resilvered == zfs_on_resilvered:
              zfs_object = lvm_volume_object_content_element
              break
    if zfs_object == None:
      zfs_object = ZFS(zfs_pool, zfs_dev, zfs_on_scrubbed, zfs_on_resilvered, zfs_scrub_interval)
    if ";" in zfs_object.pool or "," in zfs_object.pool:
      error_message = f", or ; in pool name not allowed, was '{zfs_object.pool}'"
      log.error(error_message)
      exit(error_message)
    returncode, formatted_output, formatted_response, formatted_error = exec(f"zpool list -H -o name {zfs_object.pool}")
    if len(formatted_response) == 0:
      error_message = f"a zpool with name '{zfs_object.pool}' does not exist."
      log.error(error_message)
      print(error_message)
      return
    zpool_name = formatted_response[0]
    returncode, zpool_status, formatted_response, formatted_error = exec(f"zpool status {zpool_name}")
    zfs_current_state = get_current_zfs_state(zfs_object, zpool_status)
    zfs_object.state = zfs_current_state

    if zfs_object.state.get_state() == ZFS_States.ONLINE:
      zfs_last_scrubbed = zfs_object.last_scrubbed
      if "ZEVENT_CLASS" in env_vars:
        zevent_class = env_vars["ZEVENT_CLASS"]
        if zevent_class == "sysevent.fs.zfs.scrub_finish" and env_vars["ZEVENT_POOL"] == zfs_object.pool:
          zfs_last_scrubbed = datetime.now()
          zfs_object.current_operation.state = ZFS_Operations.NONE
      if zfs_scrub_interval == None:
        zfs_scrub_interval = "3 months"
      for schedule_delta in zfs_scrub_interval.split(","):
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(schedule_delta)
        if (zfs_last_scrubbed == None or allowed_delta > zfs_last_scrubbed):
            log.info(f"zfs pool '{zpool_name}' dev '{zfs_dev}' must be scrubbed")
            if zfs_object.current_operation.state == ZFS_Operations.NONE:
              command = f"zpool scrub {zpool_name}"
              global command_list
              if command not in command_list:
                command_list.append(command)
        else:
            log.info(f"zfs pool '{zpool_name}' dev '{zfs_dev}' must not be scrubbed")
      
      zfs_object.last_scrubbed = zfs_last_scrubbed
      if "ZEVENT_POOL" in env_vars and env_vars["ZEVENT_POOL"] == zfs_object.pool:
        if zevent_class == "sysevent.fs.zfs.scrub_start":
          zfs_object.current_operation.state = ZFS_Operations.SCRUBBING
        if zevent_class == "sysevent.fs.zfs.resilver_start":
          zfs_object.current_operation.state = ZFS_Operations.RESILVERING
        if zevent_class == "sysevent.fs.zfs.resilver_finish":
          zfs_object.last_resilvered = datetime.now()
          zfs_object.current_operation.state = ZFS_Operations.NONE
    result_object = zfs_object
    result_content = None
  if result_content != None:
    for result_content_element in result_content:
      for result_content_element_key in result_content_element:
        return_object = get_config_object(result_content_element_key, result_content_element, cache_object = result_object)
        if return_object == None:
          pass
        result_object.add_content_element(return_object)
        
  return result_object



def main():
  logfile_path = '/var/run/zmirror/log.st'
  config_file_path = "/etc/zmirror/config.yml"
  cache_file_path = "/var/lib/zmirror/cache.json"
  #
  logfile_parent_directory = os.path.dirname(logfile_path)
  os.makedirs(logfile_parent_directory, exist_ok = True)
  #
  cachefile_parent_directory = os.path.dirname(cache_file_path)
  os.makedirs(cachefile_parent_directory, exist_ok = True)
  #
  logging.basicConfig(filename=logfile_path, 
            level=logging.INFO, 
            format='%(asctime)s %(levelname)-8s %(message)s',  
            datefmt='%Y-%m-%d %H:%M:%S')
  #
  log.info("starting zmirror")
  #
  global env_vars
  env_vars = dict(os.environ)
  new_all_env_vars = dict()
  for config_key, value in env_vars.items():
    if config_key[0] != "_":
      new_all_env_vars[config_key] = value
  env_vars = new_all_env_vars
  #
  with open(config_file_path) as config_file:
    # config_dict = yaml.safe_load(config_file)

    config = yaml.full_load(config_file)
    
    

    stream = Kd_Stream(sys.stdout)
    
    stream.print_obj(config)

    print()
  

  return
  if config_dict["log-env"] == "yes":
    result_string = "env" + convert_dict_to_strutex(env_vars)
    log.info(f"environment variables: {result_string}")
  config_entries = config_dict["entries"]
  thawed_json = None
  if os.path.isfile(cache_file_path):
    cache_file = open(cache_file_path, "r")
    frozen_json = json.load(cache_file)
    cache_file.close()
    thawed_json = jsonpickle.decode(frozen_json)
  if thawed_json != None:
    zmirror_state = thawed_json
  else:
    zmirror_state = ZMirrorState()
  updated_zmirror_state = ZMirrorState()
  for config_entry in config_entries:
    for config_key in config_entry:
      config_entry_object = get_config_object(config_key, config_entry, cache_object = zmirror_state)
      updated_zmirror_state.add_content_element(config_entry_object)
  frozen_json = jsonpickle.encode(updated_zmirror_state)
  cache_file = open(cache_file_path, "w")
  json.dump(frozen_json, cache_file, indent = 6)
  cache_file.close()
  return updated_zmirror_state
  
status_parser.set_defaults(func=show_status)
args = parser.parse_args()
returncode, formatted_output, formatted_response, formatted_error = exec("whoami")
try:
  if formatted_output[0] != "root":
    error_message = "You must be root!"
    log.error(error_message)
    # raise BaseException(error_message)
  args.func(args)
except Exception as exception:
  traceback.print_exc()
  error_message = str(exception)
  log.error(error_message)
  print(error_message)
  exit(error_message)
apply_commands = False
if apply_commands:
  for command in command_list:
    print(f"executing command: {command}")
    returncode, formatted_output, formatted_response, formatted_error = exec(command)
    if returncode != 0:
      currently_scrubbing = False
      for line in formatted_output:
        if "currently scrubbing" in line:
          info_message = line
          log.info(info_message)
          print(info_message)
          currently_scrubbing = True
      if not currently_scrubbing:
        error_message = f"something went wrong while executing command {command}, terminating script now"
        log.error(error_message)
        exit(error_message)
    log.info(formatted_output)
else:
  warning_message = "applying commands is currently turned off! will not scrub"
  log.warning(warning_message)
  print(warning_message)
log.info("zmirror finished!")
print("zmirror finished!")
