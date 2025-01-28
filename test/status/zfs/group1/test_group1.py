#!/bin/python3
# ******************************************************************************
# - *-coding: utf-8 -*-
# (c) copyright 2025 Alexander Poeschl
# All rights reserved.
# ******************************************************************************
# @file test_group1.py
# @author Alexander Poeschl <apoeschlfreelancing@kwanta.net>, Michael Poeschl
# @brief Pytests group1 for zmirror
# ******************************************************************************
import pytest
import time
from zmirror_dataclasses import *
from zmirror_logging import *
from pyutils import *
import zmirror_utils as zmirror_core
import threading
from zmirror import *



pyexec = exec
exec = myexec



def get_zpool_status_stub(args):
  with open("scrub_status.txt", "r") as file:
    return file.read()

# this group of tests all require the daemon running, hence they are grouped
class Test_Group1_TestMethods():
  
  # event_queue = None

  def load_event(self, json_file):
    with open(os.path.join(os.path.dirname(__file__), json_file), "r") as f:
      src = f.read()
    return json.loads(src)
#     self.event_queue.put(event)

        


  def setup_method(self, method):
    # core.config_file_path = os.pardir(__file__) + "/config.yml"
    # load_config()
    # core.cache_file_path = "./run/test/state/cache.yml"
    # self.daemon_thread = threading.Thread(target=run_command, args=(["--state-dir", "./run/state", "--config-file", f"{get_current_module_directory()}/config.yml"], ))
    # self.daemon_thread.start()
    # if self.event_queue == None:
      # self.event_queue = queue.Queue()
    pass

  
  # def teardown_method(self, method):
  
    # terminate_thread(self.daemon_thread)
    # silent_remove(core.cache_file_path)
    # pass


def trigger_event(self, name):
  event = self.load_event(os.path.join(name, ".json"))
  handle(event)

# wir testen hier allerdings nur das behandeln von events, nicht das absenden von commands

# # tatsächliches gerät wird angeschlossen

# disk taucht auf (udev: add)
def test_disk_add_serial(self):
  cache_name = "Disk|zpool-a|partition-a"
  
  assert cache_name not in zmirror_core.cache_dict

  self.trigger_event(__name__)

  dev: Disk = zmirror_core.cache_dict[cache_name]
  
  assert(dev != None)
  assert(dev.state.what == Entity_State.ONLINE)

# partition taucht auf (udev: add)
def test_partition_add(self):
  cache_name = "Partition|zpool-a|partition-a"
  
  assert cache_name not in zmirror_core.cache_dict

  self.trigger_event(__name__)

  dev: Partition = zmirror_core.cache_dict[cache_name]
  
  assert(dev != None)
  assert(dev.state.what == Entity_State.ONLINE)

# # zmirror command: zpool online vdev
# vdev wird im zpool aktiviert (vdev_online)
def test_online(self):
  cache_name = "ZFS_Blockdev_Cache|zpool-a|partition-a"

  assert cache_name not in zmirror_core.cache_dict
  
  self.trigger_event(__name__)
  
  assert cache_name in zmirror_core.cache_dict

  dev: ZFS_Blockdev = zmirror_core.cache_dict[cache_name]
  
  assert(dev != None)
  assert(dev.state.what == Entity_State.ONLINE)

# vdev beginnt zu resilvern (resilver_start)
def test_resilver_start(self):
  event = self.load_event(os.path.join(__name__, ".json"))
  handle(event)
  raise NotImplementedError

# vdev resilver ist abgeschlossen (resilver_finish)
def test_resilver_finish(self):
  self.trigger_event(__name__)
  raise NotImplementedError

# # zmirror started scrub
# pool scrub startet (scrub_start)
def test_scrub_start(self):
  zmirror_core.get_zpool_status = get_zpool_status_stub
  self.trigger_event(__name__)
  raise NotImplementedError

# pool scrub ist abgeschlossen (scrub_finish)
def test_scrub_finish(self):
  zmirror_core.get_zpool_status = get_zpool_status_stub
  self.trigger_event(__name__)
  raise NotImplementedError

# # tatsächliches gerät wird abgetrennt
# partition verschwindet (udev: remove)
def test_partition_remove(self):
  cache_name = "Partition|zpool-a|partition-a"
  
  assert cache_name not in zmirror_core.cache_dict

  self.trigger_event(__name__)

  dev: Partition = zmirror_core.cache_dict[cache_name]
  
  assert(dev != None)
  assert(dev.state.what == Entity_State.DISCONNECTED)

# disk verschwindet (udev: remove)
def test_disk_remove(self):
  cache_name = "Disk|zpool-a|partition-a"
  
  assert cache_name not in zmirror_core.cache_dict

  self.trigger_event(__name__)

  dev: Disk = zmirror_core.cache_dict[cache_name]
  
  assert(dev != None)
  assert(dev.state.what == Entity_State.DISCONNECTED)

# # zmirror command: zpool offline vdev
# vdev wird faulted (falls der zmirror command nich schneller ist)
# vdev wird disconnected (falls der zmirror command nich schneller ist... außerdem kann es sein, dass alex sich irrt und disconnected gibt es nicht im zfs speak) 
# vdev wird offline (weil zmirror den command geschickt hat)


def test_disconnected(self):
  cache_name = "ZFS_Blockdev_Cache|zpool-a|partition-a"

  assert cache_name in zmirror_core.cache_dict
  
  self.trigger_event(__name__)

  dev: ZFS_Blockdev = zmirror_core.cache_dict[cache_name]
  
  assert(dev != None)
  assert(dev.state.what == Entity_State.DISCONNECTED)


    
    # process.kill()

if __name__ == '__main__':
    if False:
        test_methods = Test_Group1_TestMethods()
        test_methods.test_some_test1()
    else:
        pytest.main()