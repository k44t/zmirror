



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
from types import SimpleNamespace

from dataclasses import dataclass

logfile_path = '/var/run/zmirror/log.st'
os.makedirs(os.path.dirname(logfile_path), exist_ok = True)
 
 # Check if systemd is available
try:
  from systemd.journal import JournalHandler
  use_journal = True
except ImportError:
  use_journal = False

# Configure the root logger
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
  handlers=[
    logging.FileHandler(logfile_path + datetime.now().strftime("%d-%m-%Y_%H:%M:%S.%f") ),  # File handler
    logging.StreamHandler(sys.stdout)   # Stream handler for stdout
  ]
)


log = logging.getLogger("zmirror")

# Add systemd journal handler if available
if use_journal:
  journal_handler = JournalHandler()
  journal_handler.setLevel(logging.INFO)
  logging.getLogger().addHandler(journal_handler)
else:
  logging.getLogger().addHandler(logging.RotatingFileHandler(logfile_path, maxBytes=65535))
  log.warning("systemd log not available")

log.info("starting zmirror")

config_file_path = "/etc/zmirror/config.yml"
cache_file_path = "/var/lib/zmirror/cache.json"
os.makedirs(os.path.dirname(cache_file_path), exist_ok = True)



cache_dict = yaml.full_load(cache_file_path)
if not isinstance(cache_dict, dict):
  cache_dict = dict()
 

class StringBuilder:
     _file_str = None

     def __init__(self):
         self._file_str = StringIO()

     def append(self, str):
         self._file_str.write(str)
         return self

     def __str__(self):
         return self._file_str.getvalue()




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
    ki_stream.print_raw("#" + self.name.lower().replace("_", "-"))


class Tabbed_Shiftex_Stream():
  def __init__(self, stream, indents = 0, level = -1):
    self.indents = indents
    self.stream = stream
    self.level = level

  def indent(self):
    self.indents = self.indents + 1

  def dedent(self):
    self.indents = self.indents - 1


  def newline(self):
    self.print_raw("\n")
    for i in range(0, self.indents):
        self.print_raw("  ")

  def newlines(self, num):
    for _ in range(0, num):
      self.newline()


  def print(self, string):
    for i, line in enumerate(string.splitlines()):
      if i > 0:
        self.newline()
      self.print_raw(line)


  def print_raw(self, string):
    self.stream.write(string)


class Kd_Stream:
  level = 0
  def __init__(self, stream):
    self.stream = stream



  def print_obj(self, obj):
    if self.level == 0:
      self.stream.print_raw("...\n")
      return
    self.level = self.level - 1
    if isinstance(obj, bool):
      if obj:
        self.stream.print_raw("yes")
      else:
        self.stream.print_raw("no")
    elif isinstance(obj, str):
      self.stream.print_raw("\"")
      for i, line in enumerate(obj.split('\n')):
        if i > 0:
          self.newline()
        self.stream.print_raw(escape_ki_string('"', line))
        # self.stream.print_raw(line)
      self.stream.print_raw("\"")
    elif isinstance(obj, numbers.Number):
      self.stream.print_raw(str(obj))
    elif isinstance(obj, datetime):
      self.stream.print_raw(obj.strftime("%Y-%m-%d'%H:%M:%S.%f"))
    elif isinstance(obj, list):
      self.stream.print_raw("[:")
      self.stream.indent()
      for i, element in enumerate(obj):
        # self.stream.print_raw("||")
        self.newline()
        # self.stream.print_raw(">>")
        self.print_obj(element)
        # self.stream.print_raw("<<")
      self.dedent()
    elif isinstance(obj, dict):
      self.stream.print_raw("{:")
      self.stream.indent()
      for i, (key, value) in enumerate(obj.items()):
        self.newline()
        self.print_obj(key)
        self.stream.print_raw(":")
        self.stream.indent()
        self.print_obj(value)
        self.dedent()
      self.dedent()
    elif obj == None:
      self.stream.print_raw("nil")
    elif hasattr(obj, "__to_kd__") and callable(obj.__to_kd__):
      obj.__to_kd__(self)
    else:
      self.print_python_obj(obj)

    self.level = self.level + 1



  def print_python_obj(self, obj):
    attrs = dir(obj)
    nattrs = []
    for attr in attrs:
      if not (attr.startswith("_") or callable(getattr(obj, attr))):
        nattrs.append(attr)
    self.print_partial_obj(obj, nattrs)

  def print_partial_obj(self, obj, props):
    if self.level == 0:
      self.stream.print_raw("...")
      return
    self.stream.print_raw(obj.__class__.__name__)
    self.stream.indent()
    if len(props) > 0:
      for prop in props:
        if hasattr(obj, prop):
          # self.stream.print_raw("..nl>")
          self.newline()
          # self.stream.print_raw("..<nl")

          # self.stream.print_raw("..>>")
          self.stream.print_raw(prop)
          self.stream.print_raw(": ")
          if callable(getattr(obj, prop)):
            self.stream.print_raw("fn ...")
          else:
            # self.stream.print_raw("|||")
            self.print_obj(getattr(obj, prop))
            # self.stream.print_raw("<<..")
    else:
      self.stream.print_raw("!")
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




outs = Tabbed_Shiftex_Stream(sys.stdout)











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


def my_constructor(loader, node):
  return loader.construct_yaml_object(node, Partition)



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



@yaml_data
class DM_Crypt:

  name: str
  key_file: str

  state: object

  content = []

  on_offline: str = None

  def get_key(self):
    return self.__cls__.name + ":" + self.name



# zmirror scrub
class DM_Crypt_States(Ki_Enum):
  DISCONNECTED = -1
  ONLINE = 1

@yaml_data
class Dated_State:
  state: object
  since: datetime

class ZFS_States(Ki_Enum):
  ERROR = -2
  DISCONNECTED = -1
  ONLINE = 1

class ZFS_Operation_States(Ki_Enum):
  NONE = 0
  SCRUBBING = 1
  RESILVERING = 2


@yaml_data
class ZFS_Blockdev_Cache:
  pool: str
  dev: str

  state = Dated_State(ZFS_States.ERROR, None)
  operation = Dated_State(ZFS_Operation_States.NONE, None)
  last_resilvered: datetime = None
  last_scrubbed: datetime = None


# zpool scrub eva
# systemctl zfs-auto-scrub-daily.interval

@yaml_data
class ZFS_Blockdev:
  pool: str
  dev: str
  on_scrubbed: str = None
  on_resilvered: str = None
  scrub_interval: str = None




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


def get_zpool_status():
  returncode, zpool_status, formatted_response, formatted_error = exec(f"zpool status {zpool_name}")
  return zpool_status

action = None



def find_or_create_cache(type, create_args=dict(), **kwargs):
  id = type.__class__.__name__
  for i, (key, value) in enumerate(kwargs.items()):
    id = id + "|" + value

  cache = None
  global cache_dict
  if id in cache_dict:
    cache = cache_dict[id]

  if not isinstance(cache, type):
    kwargs.update(create_args)
    cache = type(**kwargs)
    cache_dict[id] = cache
  return cache


def find_or_create_zfs_cache_by_vdev_path(zpool, vdev_path):
  vdev_name = vdev_path.removeprefix("/dev/mapper/").removeprefix("/dev/")
  return find_or_create_cache(ZFS_Blockdev_Cache, zpool=zpool, dev=vdev_name)

def handle(args):
  log.info("handling udev and zfs events by interpreting environment variables")
  global env

  now = datetime.now()
  if "ZEVENT_CLASS" in env:
    zevent = env["ZEVENT_SUBCLASS"]
    log.info(f"handling zfs event: {zevent}")
    zpool = env["ZEVENT_POOL"]
    zpool_status = get_zpool_status(zpool)

    # zpool event
    if zevent in ["scrub_finish", "scrub_start"]:

      regex = re.compile(rf'^\s+([a-zA-Z0-9_]+)\s+(ONLINE)\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$')

      for match in regex.finditer(zpool_status):
        dev = match.group(1)

        cache = find_or_create_cache(ZFS_Blockdev_Cache, pool=zpool, dev=dev)
        cache.operation = Dated_State(ZFS_Operation_States.NONE, now)
        if zevent == "scrub_finish":
          cache.last_scrubbed = now
        elif zevent == "scrub_start":
          cache.operation.state = ZFS_Operation_States.SCRUBBING
    # TODO: add to docs that the admin must ensure that zpool import uses /dev/mapper (dm) and /dev/vg/lv (lvm) and /dev/disk/by-partlabel (partition)
      # zpool import -d /dev/mapper -d /dev/vg/lv -d /dev/disk/by-partlabel
      # zpool create my-pool mirror /dev/vg-my-vg/my-lv /dev/disk/by-partlabel/my-partition /dev/mapper/my-dm-crypt

    # zpool-vdev event
    elif zevent in ["vdev_online", "statechange"]:
      # possible cases:
        # ZEVENT_POOL:: mypoolname
        # ZEVENT_VDEV_PATH:: /dev/mapper/mypoolname-b-main
        # ZEVENT_VDEV_PATH:: /dev/{vg_bak_gamma/lv_bak_gamma}
        # ZEVENT:: /dev/{sda3}
        # ZEVENT:: /dev/disk/by-partlabel/mypartlabel
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(vdev_path)
      if zevent == "vdev_online":
        cache.state = Dated_State(ZFS_States.ONLINE, now)
      elif zevent == "statechange":
        if env["ZEVENT_VDEV_STATE_STR"] == "OFFLINE":
          cache.state = Dated_State(ZFS_States.DISCONNECTED, now)
        else:
          log.warning(f"(potential bug) unknown statechange event: {env["ZEVENT_VDEV_STATE_STR"]}")
          cache.state = Dated_State(ZFS_States.ERROR, now)

    # zool-vdev event
    elif zevent in ["resilver_start", "resilver_finish"]:
      vdev_path = env["ZEVENT_VDEV_PATH"]
      cache = find_or_create_zfs_cache_by_vdev_path(vdev_path)
      cache.operation = Dated_State(ZFS_Operation_States.NONE, now)
      if zevent == "resilver_start":
        cache.operation = Dated_State(ZFS_Operation_States.RESILVERING, now)
      elif zevent == "resilver_finish":
        cache.operation = Dated_State(ZFS_Operation_States.NONE, now)
        cache.last_resilvered = now

  elif ("DEVTYPE" in env):
    action = env["ACTION"]
    devtype = env["DEVTYPE"]
    log.info(f"handling udev block event: {action}")
    if devtype == "disk":
      if "ID_SERIAL" in env:
        cache = find_or_create_cache(Disk, serial=env["ID_SERIAL"])
      elif "DM_NAME" in env:
        cache = find_or_create_cache(Disk, name=env["DM_NAME"])
    elif devtype == "partition":
      cache = find_or_create_cache(Partition, name=env["PARTNAME"])
    if cache != None:
      if action == "add":
        cache.state = Dated_State(DM_Crypt_States.ONLINE, now)
      elif action == "remove":
        cache.state = Dated_State(DM_Crypt_States.DISCONNECTED, now)

  save_cache()



# zmirror trim-cache

def copy_to_cache(conf, cache):
  for prop in dir(conf):
    setattr(cache, prop, getattr(conf, prop))






# yaml.dump(config)











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
pyexec = exec
exec = myexec





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




# zmirror scrub
def scrub(args):
  log.info("starting zfs scrubs if necessary")
  def possibly_scrub(dev):
    if isinstance(dev, ZFS_Blockdev):
      cache = find_or_create_cache(ZFS_Blockdev_Cache, pool=dev.pool, dev=dev.dev)
      if dev.scrub_interval != None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(dev.scrub_interval)
        if (cache.last_scrubbed == None or allowed_delta > cache.last_scrubbed):
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' must be scrubbed")
          if cache.operation != None and cache.operation.state == ZFS_Operation_States.NONE:
            execute_command(f"zpool scrub {dev.pool}")
        else:
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' does not have to be scrubbed")
  zmirror = load_config()
  iterate_content_tree(zmirror, possibly_scrub)




def execute_command(command):
  apply_commands = False
  if apply_commands:
    log.info(f"executing command: {command}")
    returncode, formatted_output, formatted_response, formatted_error = exec(command)
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




# env will only be logged if zmirror is called without arguments, and the config setting is set
def log_env():
  global env
  stream = Tabbed_Shiftex_Stream(sys.stdout)
  for var in env:
    if not var.startswith("_"):
      stream.print_raw(f"{var}:: ")
      stream.indent()
      stream.print_indented(env[var])
      stream.dedent()




def load_config():
  global config
  with open(config_file_path) as config_file:
    # config_dict = yaml.safe_load(config_file)

    config = yaml.full_load(config_file)

    stream = Kd_Stream(outs)

    outs.newlines(3)
    outs.print("config")
    outs.print("#####################")
    outs.newlines(2)

    stream.print_obj(config)
    return config




def clear_cache():
  global cache_file_path
  os.remove(cache_file_path)





def save_cache():
  yaml.dump(cache_dict, cache_file_path)

#


env = dict(os.environ)
#


# Create the parser
parser = argparse.ArgumentParser(description="zmirror")
subparser = parser.add_subparsers(required=True)


# nice to have, maybe?: zmirror trigger        # simulates events or something...


# nice to have: zmirror prune-cache    # called by user
# prune_parser = subparser.add_parser('prune-cache', parents=[], help='remove cache entries that are not also present in config')
# prune_parser.set_defaults(func=prune_cache)

clear_cache_parser = subparser.add_parser('clear-cache', parents=[], help= 'clear cache')
clear_cache_parser.set_defaults(func=clear_cache)

# zmirror status   # called by user
#status_parser = subparser.add_parser('status', parents=[], help='show status of zmirror')
#status_parser.set_defaults(func=show_status)


# zmirror scrub   # called by systemd.timer
scrub_parser = subparser.add_parser('scrub', help='start pending scrubs')
scrub_parser.set_defaults(func=scrub)

# zmirror    # without args
parser.set_defaults(func=handle)

args = parser.parse_args()

try:
  args.func(args)
except Exception as exception:
  traceback.print_exc()
  error_message = str(exception)
  log.error(error_message)

  outs.newlines(3)
  outs.print("error")
  outs.print("################")
  outs.newlines(2)
  outs.print(error_message)
  exit(error_message)

log.info("zmirror finished!")
