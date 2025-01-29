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
import os
import json
import inspect



pyexec = exec
exec = myexec



zfs_blockdev_id = "ZFS_Blockdev_Cache|zpool-a|partition-a"
partition_id = "Partition|partition-a"
dm_id= "DM_Crypt|dm-alpha"
disk_id = "Disk|0123456789abcdef"
zpool_id = "ZPool|zpool-a"


def open_local(file, mode):
  filepath = os.path.join(os.path.dirname(__file__), file)
  return open(filepath, mode)

def get_zpool_status_stub(args):
  with open_local("scrub_status.txt", "r") as file:
    return file.read()



def trigger_event(name):
  event = load_event(name + ".json")
  handle(event)

def load_event(json_file):
  with open_local(json_file, "r") as f:
    src = f.read()
  return json.loads(src)
#     self.event_queue.put(event)



# this group of tests all require the daemon running, hence they are grouped
class Test_Group1_TestMethods():


  # event_queue = None

        


  def setup_method(self, method):
    # we use a stub method. this is only relevant for the scrub events
    zmirror_core.get_zpool_status = get_zpool_status_stub

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



  # wir testen hier allerdings nur das behandeln von events, nicht das absenden von commands

  # # tatsächliches gerät wird angeschlossen

  # disk taucht auf (udev: add)
  def test_disk_add(self):
    
    assert disk_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Disk = zmirror_core.cache_dict[disk_id]
    
    assert(dev != None)
    assert(dev.state.what == Entity_State.ONLINE)

  # partition taucht auf (udev: add)
  def test_partition_add(self):
    
    assert partition_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Partition = zmirror_core.cache_dict[partition_id]
    
    assert(dev != None)
    assert(dev.state.what == Entity_State.ONLINE)

  # # zmirror command: zpool online vdev
  # vdev wird im zpool aktiviert (vdev_online)
  def test_zdev_online(self):
    assert zfs_blockdev_id not in zmirror_core.cache_dict
    trigger_event(inspect.currentframe().f_code.co_name)
    assert zfs_blockdev_id in zmirror_core.cache_dict
    dev: ZFS_Blockdev_Cache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev != None)
    assert(dev.state.what == Entity_State.ONLINE)


  # vdev beginnt zu resilvern (resilver_start)
  def test_resilver_start(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFS_Blockdev_Cache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev != None)
    assert(dev.operation.what== ZFS_Operation_State.RESILVERING)

  # vdev resilver ist abgeschlossen (resilver_finish)
  def test_resilver_finish(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFS_Blockdev_Cache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev != None)
    assert(dev.operation.what == ZFS_Operation_State.NONE)

  # # zmirror started scrub
  # pool scrub startet (scrub_start)
  def test_scrub_start(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFS_Blockdev_Cache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev != None)
    assert(dev.operation.what == ZFS_Operation_State.SCRUBBING)

  # pool scrub ist abgeschlossen (scrub_finish)
  def test_scrub_finish(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFS_Blockdev_Cache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev != None)
    assert(dev.operation.what == ZFS_Operation_State.NONE)

  # # tatsächliches gerät wird abgetrennt
  # partition verschwindet (udev: remove)
  def test_partition_remove(self):
    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Partition = zmirror_core.cache_dict[partition_id]
    
    assert(dev != None)
    assert(dev.state.what == Entity_State.DISCONNECTED)

  # disk verschwindet (udev: remove)
  def test_disk_remove(self):
    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Disk = zmirror_core.cache_dict[disk_id]
    
    assert(dev != None)
    assert(dev.state.what == Entity_State.DISCONNECTED)

  # # zmirror command: zpool offline vdev
  # vdev wird faulted (falls der zmirror command nich schneller ist)
  # vdev wird disconnected (falls der zmirror command nich schneller ist... außerdem kann es sein, dass alex sich irrt und disconnected gibt es nicht im zfs speak) 
  # vdev wird offline (weil zmirror den command geschickt hat)


  def test_zdev_disconnected(self):
    assert zfs_blockdev_id in zmirror_core.cache_dict
    
    trigger_event(inspect.currentframe().f_code.co_name)

    dev: ZFS_Blockdev = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev != None)
    assert(dev.state.what == Entity_State.DISCONNECTED)


    
    # process.kill()

if __name__ == '__main__':
    if False:
        test_methods = Test_Group1_TestMethods()
        test_methods.test_some_test1()
    else:
        pytest.main()