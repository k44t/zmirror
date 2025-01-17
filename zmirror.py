



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


log = logging.getLogger(__name__)



# Create the parser
parser = argparse.ArgumentParser(description="zmirror worker")
status_parser = parser.add_parser('status', parents=[], help='show status of zmirror')


def convert_dict_to_strutex(dictionary):
  for key, value in dictionary.items():
    result_string = result_string + f"\n\t{key}:: {value}"
  return result_string

class Content_Elements(object):
  def __init__(self, content_elements = []):
    self.content_elements = content_elements
  def add_content_element(self, content_element):
    self.content_elements.append(content_element)

class Content_Element(object):
  def __init__(self, tag):
    self.tag = tag

class Content_Element_with_Content_Elements(Content_Element):
  def __init__(self, tag, content_elements):
    super(Content_Element_with_Content_Elements, self).__init__(tag)
    self.content_elements = Content_Elements(content_elements)
  def add_content_element(self, content_element):
    self.content_elements.add_content_element(content_element)


class ZMirrorState(Content_Element_with_Content_Elements):
  def __init__(self, content_elements):
    super(ZMirrorState, self).__init__("zmirror_state", content_elements)

class Config_Entry(Content_Element_with_Content_Elements):
  def __init__(self, tag, content_elements):
    super(Config_Entry, self).__init__("partition", content_elements)
    self.tag = tag

class Partition(Config_Entry):
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
    super(Lvm_Volume_Group, self).__init__("lvm_volume_group", name, on_offline, content_elements)

class Lvm_Volume(On_Offline_Content_Element):
  def __init__(self, name, on_offline, content_elements = []):
    super(Lvm_Volume_Group, self).__init__("lvm_volume", name, on_offline, content_elements)


class Dm_Crypt_States(Enum):
  DISCONNECTED = -1
  ONLINE = 1

class Dm_Crypt_State(object):
  def __init__(self, state = Dm_Crypt_States.DISCONNECTED):
    if state not in Dm_Crypt_States.__members__:
      log.error(f"Dm_Crypt_State `{state}` does not exist. Program will terminate.")
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
    if state not in Scrubb_States.__members__:
      log.error(f"Scrubb_State `{state}` does not exist. Program will terminate.")
      exit()
    else:
      self.state = Scrubb_States(state)
    self.since = datetime.now()
  def get_scrubb_state_name(self):
    since = self.since.strftime("%Y-%m-%d %H:%M:%SZ")
    if self.state == Scrubb_States.NOT_REQUESTED:
      return f"not-requested since: {since}"
    if self.state == Scrubb_States.PENDING:
      return f"pending since: {since}"
    if self.state == Scrubb_States.OVERDUE:
      return f"overdue since: {since}"


class Dm_Crypt(Content_Element_with_Content_Elements):
  def __init__(self, name, key_file, content_elements = []):
    super(Dm_Crypt, self).__init__("dm_crypt", content_elements)
    self.name = name
    self.key_file = key_file
    self.scrubb_state = Scrubb_State()
    self.dm_crypt_state = Dm_Crypt_State()

class ZFS_States(Enum):
  DISCONNECTED = -1
  PRESENT_BUT_OFFLINE = 0
  ONLINE = 1

class ZFS_State(object):
  def __init__(self, state = ZFS_States.DISCONNECTED):
    if state not in ZFS_States.__members__:
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

class ZFS_Operations(Enum):
  NONE = 0
  SCRUBBING = 1
  RESILVERING = 2

class ZFS_Operation(object):
  def __init__(self, state = ZFS_Operations.NONE):
    if state not in ZFS_Operations.__members__:
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

def show_status(args):
  zmirror_state = main()
  for zmirror_content_element in zmirror_state.content_elements:
    for config_entry_element in zmirror_content_element.content_elements:
      for dm_crypt_element in config_entry_element.content_elements:
        log.info(f"{dm_crypt_element.name} @{dm_crypt_element.tag}: {dm_crypt_element.scrubb_state.get_scrubb_state_string()}")
        for zpool_element in dm_crypt_element.content_elements:
          for volume_element in zpool_element.content_elements:
            for lvm_volume_group_element in volume_element.content_elements:
              for lvm_volume_element in lvm_volume_group_element.content_elements:
                for zfs_element in lvm_volume_element.content_elements:
                  log_message = f"""
                    {zfs_element.dev} @ZFS: {zfs_element.state.get_state_name()}

                    operation: {zfs_element.current_operation.active_operation.get_operation_string()}

                    last resilvered: '{zfs_element.last_resilvered.strftime("%Y-%m-%d %H:%M:%SZ")}'
                    last scrubbed: '{zfs_element.last_resilvered.strftime("%Y-%m-%d %H:%M:%SZ")}'

                    scrub: {zfs_element.scrubb_state.get_scrubb_state_string()}
                  """
                  log.info(log_message)

def get_current_zfs_state(zfs_object, zpool_status):
  global env_vars
  zevent_class = env_vars["ZEVENT_CLASS"]
  if zevent_class == "sysevent.fs.zfs.scrub_finish":
    regexp_pattern = rf'{zfs_object.name}\s+ONLINE\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$'
    regexp_searcher = re.compile(regexp_pattern)
    dev_status = regexp_searcher.search(zpool_status).groups()[0]
    if dev_status != "":
      return ZFS_States.ONLINE
    regexp_pattern = rf'{zfs_object.name}\s+OFFLINE\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$'
    regexp_searcher = re.compile(regexp_pattern)
    dev_status = regexp_searcher.search(zpool_status).groups()[0]
    if dev_status != "":
      return ZFS_States.PRESENT_BUT_OFFLINE
  if zevent_class == "resource.fs.zfs.statechange":
    if zevent_class["ZEVENT_VDEV_STATE_STR"] == "OFFLINE":
      return ZFS_States.DISCONNECTED
  if zevent_class == "sysevent.fs.zfs.vdev_online":
    return ZFS_States.ONLINE

def main():
  logfile_path = '/var/run/zmirror/log.st'
  config_file_path = "/etc/zmirror/config.yml"
  cache_file_path = "/var/lib/zmirror/cache.json"
  command_list = []
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
      config_entry_object = None
      if config_key == "partition":
        partition = config_entry[config_key]
        partition_name = partition["name"]
        content = partition["content"]
        zmirror_content_elements = zmirror_state.content_elements
        for zmirror_content_element in zmirror_content_elements:
          if zmirror_content_element.tag == config_key:
            zmirror_partition_object = zmirror_content_element
            if zmirror_partition_object.name == partition_name:
              config_entry_object = zmirror_partition_object
              break
        if config_entry_object == None:
          config_entry_object = Partition(partition_name)
      if config_key == "disk":
        disk = config_entry[config_key]
        disk_serial = disk["serial"]
        content = disk["content"]
        zmirror_content_elements = zmirror_state.content_elements
        for zmirror_content_element in zmirror_content_elements:
          if zmirror_content_element.tag == config_key:
            zmirror_disk_object = zmirror_content_element
            if zmirror_disk_object.name == disk_serial:
              config_entry_object = zmirror_disk_object
              break
        if config_entry_object == None:
          config_entry_object = Disk(disk_serial)
      
      dm_crypt = content["dm-crypt"]
      dm_crypt_name = dm_crypt["name"]
      dm_crypt_key_file = dm_crypt["key-file"]
      dm_crypt_content = dm_crypt["content"]
      # config_entry_object is either a disk or a partition:
      config_entry_object_content_elements = config_entry_object.content_elements
      for config_entry_object_content_element in config_entry_object_content_elements:
        if config_entry_object_content_element.tag == "dm_crypt":
          if config_entry_object_content_element.name == dm_crypt_name:
            if config_entry_object_content_element.key_file == dm_crypt_key_file:
              dm_crypt_object = config_entry_object_content_element
              break
      if dm_crypt_object == None:
        dm_crypt_object = Dm_Crypt(dm_crypt_name, dm_crypt_key_file)
      if ("DEVTYPE" in env_vars) \
        and (env_vars["DEVTYPE"] == "disk" \
          and (("ID_SERIAL" in env_vars and env_vars["ID_SERIAL"] == config_entry_object.serial) \
          or ("DM_NAME" in env_vars and config_entry_object.name in env_vars["DM_NAME"]))) \
        or (env_vars["DEVTYPE"] == "partition" \
          and env_vars["PARTNAME"] == config_entry_object.name): #alexTODO: prüfen ob das mit dem partname eh so passt mit config_entry_object.name
          if env_vars["ACTION"] == "add":
            dm_crypt_object.dm_crypt_state.state = Dm_Crypt_States.ONLINE
          if env_vars["ACTION"] == "remove":
            dm_crypt_object.dm_crypt_state.state = Dm_Crypt_States.DISCONNECTED

      for dm_crypt_content_element in dm_crypt_content:
        for dm_crypt_content_tag in dm_crypt_content_element:
          if dm_crypt_content_tag == "zpool":
            zpool = dm_crypt_content_element[dm_crypt_content_tag]
            zpool_name = zpool["name"]
            zpool_on_offline = zpool["on-offline"]
            zpool_content = zpool["content"]
            dm_crypt_object_content_elements = dm_crypt_object.content_elements
            for dm_crypt_object_content_element in dm_crypt_object_content_elements:
              if dm_crypt_object_content_element.tag == dm_crypt_content_tag:
                if dm_crypt_object_content_element.name == dm_crypt_name:
                  if dm_crypt_object_content_element.on_offline == zpool_on_offline:
                    zpool_object = dm_crypt_object_content_element
                    break
            if zpool_object == None:
              zpool_object = ZPool(zpool_name, zpool_on_offline)
            
            returncode, zpool_status, formatted_response, formatted_error = exec(f"zpool status {zpool_object.name}")
            for zpool_content_element in zpool_content:
              for zpool_content_key in zpool_content_element:
                if zpool_content_key == "volume":
                  volume = zpool_content_element[zpool_content_key]
                  volume_name = volume["name"]
                  volume_on_offline = volume["on-offline"]
                  volume_content = volume["content"]
                  zpool_object_content_elements = zpool_object.content_elements
                  for zpool_object_content_element in zpool_object_content_elements:
                    if zpool_object_content_element.tag == dm_crypt_content_tag:
                      if zpool_object_content_element.name == dm_crypt_name:
                        if zpool_object_content_element.on_offline == zpool_on_offline:
                          volume_object = zpool_object_content_element
                          break
                  if volume_object == None:
                    volume_object = Volume(volume_name, volume_on_offline)
                  for volume_content_element in volume_content:
                    for volume_content_key in volume_content_element:
                      if volume_content_key == "lvm-volume-group":
                        lvm_volume_group = volume_content_element[volume_content_key]
                        lvm_volume_group_name = lvm_volume_group["name"]
                        lvm_volume_group_on_offline = lvm_volume_group["on-offline"]
                        lvm_volume_group_content = lvm_volume_group["content"]
                        volume_object_content_elements = volume_object.content_elements
                        for volume_object_content_element in volume_object_content_elements:
                          if volume_object_content_element.tag == dm_crypt_content_tag:
                            if volume_object_content_element.name == dm_crypt_name:
                              if volume_object_content_element.on_offline == zpool_on_offline:
                                lvm_volume_group_object = volume_object_content_element
                                break
                        if lvm_volume_group_object == None:
                          lvm_volume_group_object = Lvm_Volume_Group(lvm_volume_group_name, lvm_volume_group_on_offline)
                        for lvm_volume_group_content_element in lvm_volume_group_content:
                          for lvm_volume_group_content_key in lvm_volume_group_content_element:
                            if lvm_volume_group_content_key == "lvm-volume":
                              lvm_volume = lvm_volume_group_content_element[lvm_volume_group_content_key]
                              lvm_volume_name = lvm_volume["name"]
                              lvm_volume_on_offline = lvm_volume["on-offline"]
                              lvm_volume_content = lvm_volume["content"]
                              lvm_volume_group_object_content_elements = lvm_volume_group_object.content_elements
                              for lvm_volume_group_object_content_element in lvm_volume_group_object_content_elements:
                                if lvm_volume_group_object_content_element.tag == dm_crypt_content_tag:
                                  if lvm_volume_group_object_content_element.name == dm_crypt_name:
                                    if lvm_volume_group_object_content_element.on_offline == zpool_on_offline:
                                      lvm_volume_object = lvm_volume_group_object_content_element
                                      break
                              if lvm_volume_object == None:
                                lvm_volume_object = Lvm_Volume(lvm_volume_name, lvm_volume_on_offline)
                              for lvm_volume_content_element in lvm_volume_content:
                                for lvm_volume_content_key in lvm_volume_content_element:
                                  if lvm_volume_content_key == "lvm-volume":
                                    zfs = lvm_volume_content_element[lvm_volume_content_key]
                                    zfs_pool = zfs["pool"]
                                    zfs_dev = zfs["dev"]
                                    if "on-scrubbed" in zfs:
                                      zfs_on_scrubbed = zfs["on-scrubbed"]
                                    if "on-resilvered" in zfs:
                                      zfs_on_resilvered = zfs["on-resilvered"]
                                    if "scrub-interval" in zfs:
                                      zfs_scrub_interval = zfs["scrub-interval"]
                                    lvm_volume_object_content_elements = lvm_volume_object.content_elements
                                    for lvm_volume_object_content_element in lvm_volume_object_content_elements:
                                      if lvm_volume_object_content_element.pool == zfs_pool:
                                        if lvm_volume_object_content_element.dev == zfs_dev:
                                          if lvm_volume_object_content_element.on_scrubbed == zfs_on_scrubbed:
                                            if lvm_volume_object_content_element.on_resilvered == zfs_on_resilvered:
                                              zfs_object = lvm_volume_object_content_element
                                              break
                                    if zfs_object == None:
                                      zfs_object = ZFS(zfs_pool, zfs_dev, zfs_on_scrubbed, zfs_on_resilvered, zfs_scrub_interval)

                                    zfs_current_state = get_current_zfs_state(zfs_object, zpool_status)
                                    zfs_object.state = zfs_current_state

                                    if zfs_object.state == ZFS_States.ONLINE:
                                      zfs_last_scrubbed = zfs_object.last_scrubbed
                                      zevent_class = env_vars["ZEVENT_CLASS"]
                                      if zevent_class == "sysevent.fs.zfs.scrub_finish" and env_vars["ZEVENT_POOL"] == zfs_object.pool:
                                        zfs_last_scrubbed = datetime.now()
                                        zfs_object.current_operation.state = ZFS_Operations.NONE
                                      for schedule_delta in zfs_scrub_interval.split(","):
                                        # parsing the schedule delta will result in a timestamp calculated from now
                                        allowed_delta = dateparser.parse(schedule_delta)
                                        if (allowed_delta > zfs_last_scrubbed):
                                            log.info(f"zfs pool '{zfs_pool}' dev '{zfs_dev}' must be scrubbed")
                                            if zfs_object.current_operation.active_operation == ZFS_Operations.NONE:
                                              command = f"zpool scrub {zfs_pool}"
                                              if command not in command_list:
                                                command_list.append(command)
                                        else:
                                            log.info(f"zfs pool '{zfs_pool}' dev '{zfs_dev}' must not be scrubbed")
                                      
                                      zfs_object.last_scrubbed = zfs_last_scrubbed
                                      if env_vars["ZEVENT_POOL"] == zfs_object.pool:
                                        if zevent_class == "sysevent.fs.zfs.scrub_start":
                                          zfs_object.current_operation.state = ZFS_Operations.SCRUBBING
                                        if zevent_class == "sysevent.fs.zfs.resilver_start":
                                          zfs_object.current_operation.state = ZFS_Operations.RESILVERING
                                        if zevent_class == "sysevent.fs.zfs.resilver_finish":
                                          zfs_object.last_resilvered = datetime.now()
                                          zfs_object.current_operation.state = ZFS_Operations.NONE
                                    lvm_volume_object.add_content_element(zfs_object)
                              lvm_volume_group_object.add_content_element(lvm_volume_object)
                        volume_object.add_content_element(lvm_volume_group_object)
                  zpool_object.add_content_element(volume_object)
            dm_crypt_object.add_content_element(zpool_object)
      config_entry_object.add_content_element(dm_crypt_object)
      updated_zmirror_state.add_content_element(config_entry_object)
      frozen_json = jsonpickle.encode(updated_zmirror_state)
      cache_file = open(cache_file_path, "w")
      json.dump(frozen_json, cache_file, indent = 6)
      cache_file.close()
      apply_commands = False
      if apply_commands:
        for command in command_list:
          returncode, formatted_output, formatted_response, formatted_error = exec(command)
          if returncode != 0:
            error_message = f"something went wrong while executing command {command}, terminating script now"
            log.error(error_message)
            exit(error_message)
          log.info(formatted_output)
      else:
        log.warning("applying commands is currently turned off! will not scrub")
      return updated_zmirror_state

            


  
status_parser.set_defaults(func=show_status)

"""
ACTION:: remove

ACTION:: add

DEVTYPE:: disk
ID_SERIAL:: TOSHIBA_MG09ACA18TE_71L0A33JFQDH

DEVTYPE:: disk
DM_VG_NAME:: vg-eva-bak-gamma
DM_LV_NAME:: lv-eva-bak-gamma
ID_FS_LABEL:: eva
DM_NAME:: vg--eva--bak--gamma-lv--eva--bak--gamma

DEVTYPE:: partition
PARTNAME:: eva-b-swap


ZEVENT_CLASS:: sysevent.fs.zfs.resilver_start

ZEVENT_CLASS:: sysevent.fs.zfs.resilver_finish


ZEVENT_CLASS:: sysevent.fs.zfs.vdev_online

ZEVENT_CLASS:: resource.fs.zfs.statechange
ZEVENT_VDEV_STATE_STR:: OFFLINE

ZEVENT_CLASS:: sysevent.fs.zfs.scrub_start

ZEVENT_CLASS:: sysevent.fs.zfs.scrub_finish

zpool status eva

[^\s]
f"{name}\s+ONLINE\s+[0-9]\s+[0-9]\s+[0-9]\s*.*$"
"""