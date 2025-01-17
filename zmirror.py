



import os, stat, os.path
import shutil
import re
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

class Content_Elements(object):
  def __init__(self, content_elements = []):
    self.content_elements = content_elements
  def add_content_element(self, content_element):
    self.content_elements.append(content_element)
  def get_all_content_elements(self):
    return self.content_elements

class Content_Element(object):
  def __init__(self, tag):
    self.tag = tag

class Content_Element_with_Content_Elements(Content_Element):
  def __init__(self, tag, content_elements):
    super(Content_Element_with_Content_Elements, self).__init__(tag)
    self.content_elements_object = Content_Elements(content_elements)
  def add_content_element(self, content_element):
    self.content_elements_object.add_content_element(content_element)
  def get_all_content_elements(self):
    return self.content_elements_object.get_all_content_elements()


class ZMirrorState(Content_Element_with_Content_Elements):
  def __init__(self, content_elements = []):
    super(ZMirrorState, self).__init__("zmirror_state", content_elements)

class Config_Entry(Content_Element_with_Content_Elements):
  def __init__(self, tag, content_elements = []):
    super(Config_Entry, self).__init__("partition", content_elements)
    self.tag = tag

class Partition(Config_Entry):
  # for some weird reason we it is not enough to give an empty list as content_elements, as content_elements will falsely be containing something in the second round (eva-b-main contained eva-a-main in content_elements even if this should have been an empty list then, therefore when calling for initializing a partition, give content_elements as empty list)
  def __init__(self, name, content_elements = []):
    super(Partition, self).__init__("partition", content_elements)
    self.name = name

class Disk(Config_Entry):
  def __init__(self, serial, content_elements = []):
    super(Disk, self).__init__("disk", content_elements)
    self.serial = serial


class On_Offline_Content_Element(Content_Element_with_Content_Elements):
  def __init__(self, tag, name, on_offline, content_elements = []):
    super(On_Offline_Content_Element, self).__init__(tag, content_elements)
    self.name = name
    self.on_offline = on_offline
   

class ZPool(On_Offline_Content_Element):
  def __init__(self, name, on_offline, content_elements = []):
    super(ZPool, self).__init__("zpool", name, on_offline, content_elements)

class Volume(On_Offline_Content_Element):
  def __init__(self, name, on_offline, content_elements = []):
    super(Volume, self).__init__("volume", name, on_offline, content_elements)

class Lvm_Volume_Group(On_Offline_Content_Element):
  def __init__(self, name, on_offline, content_elements = []):
    super(Lvm_Volume_Group, self).__init__("lvm-volume-group", name, on_offline, content_elements)

class Lvm_Volume(On_Offline_Content_Element):
  def __init__(self, name, on_offline, content_elements = []):
    super(Lvm_Volume, self).__init__("lvm-volume", name, on_offline, content_elements)


class Dm_Crypt_States(Enum):
  DISCONNECTED = -1
  ONLINE = 1

class Dm_Crypt_State(object):
  def __init__(self, state = Dm_Crypt_States.DISCONNECTED):
    if state.name not in Dm_Crypt_States.__members__:
      log.error(f"Dm-Crypt-State `{state}` does not exist. Program will terminate.")
      exit()
    else:
      self.state = Dm_Crypt_States(state)
  def get_state_name(self):
    if self.state == Dm_Crypt_States.DISCONNECTED:
      return "disconnected"
    if self.state == Dm_Crypt_States.ONLINE:
      return "online"

class Scrubb_States(Enum):
  NOT_REQUESTED = 0
  PENDING = 1
  OVERDUE = 2

class Scrubb_State(object):
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


class Dm_Crypt(Content_Element_with_Content_Elements):
  def __init__(self, name, key_file, content_elements = []):
    super(Dm_Crypt, self).__init__("dm-crypt", content_elements)
    self.name = name
    self.key_file = key_file
    self.scrubb_state = Scrubb_State()
    self.dm_crypt_state = Dm_Crypt_State()

class ZFS_States(Enum):
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

class ZFS_Operations(Enum):
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



class ZFS(object):
  def __init__(self, pool, dev, on_scrubbed, on_resilvered, scrub_interval = "3 months"):
    self.tag = "zfs"
    self.pool = pool
    self.dev = dev
    self.name = self.dev.split("/")[0]
    self.on_scrubbed = on_scrubbed
    self.on_resilvered = on_resilvered
    self.current_operation = ZFS_Operation()
    self.state = ZFS_State()
    self.scrubb_state = Scrubb_State()
    self.last_resilvered = None
    self.last_scrubbed = None
    self.scrub_interval = scrub_interval
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
      dm_crypt_object = Dm_Crypt(dm_crypt_name, dm_crypt_key_file, content_elements=[])
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
        on_offline_element_object = Volume(on_offline_element_name, on_offline_element_on_offline, content_elements=[])
      elif  tag == "zpool":
        on_offline_element_object = ZPool(on_offline_element_name, on_offline_element_on_offline, content_elements=[])
      elif  tag == "lvm-volume-group":
        on_offline_element_object = Lvm_Volume_Group(on_offline_element_name, on_offline_element_on_offline, content_elements=[])
      elif  tag == "lvm-volume":
        on_offline_element_object = Lvm_Volume(on_offline_element_name, on_offline_element_on_offline, content_elements=[])
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
      config_entry_object = Disk(disk_serial, content_elements=[])
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
        partition_partition_object = partition_content_element
        if partition_partition_object.name == partition_name:
          partition_object = partition_partition_object
          break
    if partition_object == None:
      # for some weird reason we need to give an empty list as content_elements, as otherwise content_elements will falsely be containing something in the second round (eva-b-main contained eva-a-main in content_elements even if this should have been an empty list then)
      partition_object = Partition(partition_name, content_elements = [])
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
        result_object.add_content_element(return_object)
        
  return result_object



def main():
  logfile_path = '/var/run/zmirror/log.st'
  config_file_path = "/etc/zmirror/config.yml"
  cache_file_path = "/var/lib/zmirror/cache.json"
  logfile_parent_directory = os.path.dirname(logfile_path)
  os.makedirs(logfile_parent_directory, exist_ok = True)
  cachefile_parent_directory = os.path.dirname(cache_file_path)
  os.makedirs(cachefile_parent_directory, exist_ok = True)
  logging.basicConfig(filename=logfile_path, 
            level=logging.INFO, 
            format='%(asctime)s %(levelname)-8s %(message)s',  
            datefmt='%Y-%m-%d %H:%M:%S')
  log.info("starting zmirror")
  global env_vars
  env_vars = dict(os.environ)
  new_all_env_vars = dict()
  for config_key, value in env_vars.items():
    if config_key[0] != "_":
      new_all_env_vars[config_key] = value
  env_vars = new_all_env_vars
  with open(config_file_path) as config_file:
    config_dict = yaml.safe_load(config_file)
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
    raise BaseException(error_message)
  args.func(args)
except Exception as exception:
  traceback.print_exc()
  error_message = str(exception)
  log.error(error_message)
  print(error_message)
  exit(error_message)
apply_commands = True
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
