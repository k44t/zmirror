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
from zmirror_daemon import handle
import threading
from zmirror import *
import os
import json
import inspect
from datetime import datetime
import zmirror_commands as zmirror_commands


pyexec = exec
exec = myexec



zfs_blockdev_id = "ZFSBackingBlockDeviceCache|zpool-a|partition-a"
partition_id = "Partition|partition-a"
dm_id= "DM_Crypt|dm-alpha"
disk_id = "Disk|0123456789abcdef"
zpool_id = "ZPool|zpool-a"
virtual_disk_id = "VirtualDisk|0123456789abcdef"
zfs_volume_id = "ZFSVolume|zpool-a|path/zfs-volume"
logical_volume_id = "LVMLogicalVolume|vg-alpha|lv-1"



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

def do_nothing(*args):
  pass


# this group of tests all require the daemon running, hence they are grouped
class Test_Group1_TestMethods():


  # event_queue = None

        


  def setup_method(self, method):
    # we use a stub method. this is only relevant for the scrub events
    zmirror_core.get_zpool_status = get_zpool_status_stub
    zmirror_core.execute_commands = do_nothing

    # core.config_file_path = os.pardir(__file__) + "/config.yml"
    # load_config()
    # core.cache_file_path = "./run/test/state/cache.yml"
    # self.daemon_thread = threading.Thread(target=run_command, args=(["--state-dir", "./run/state", "--config-file", f"{get_current_module_directory()}/config.yml"], ))
    # self.daemon_thread.start()
    # if self.event_queue == None:
      # self.event_queue = queue.Queue()
    pass

  
  def teardown_method(self, method):
  
    # terminate_thread(self.daemon_thread)
    # silent_remove(core.cache_file_path)
    # pass
    zmirror_commands.commands = []



  # # tatsächliches gerät wird angeschlossen

  # disk taucht auf (udev: add)
  def test_disk_add(self):

    assert disk_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Disk = zmirror_core.cache_dict[disk_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

    # assert("zpool offline xyz" in zmirror_commands.commands)


  # partition taucht auf (udev: add)
  def test_partition_add(self):
    
    assert partition_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Partition = zmirror_core.cache_dict[partition_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

  # # zmirror command: zpool online vdev
  # vdev wird im zpool aktiviert (vdev_online)
  def test_zdev_online(self):
    assert zfs_blockdev_id not in zmirror_core.cache_dict
    trigger_event(inspect.currentframe().f_code.co_name)
    assert zfs_blockdev_id in zmirror_core.cache_dict
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)


  # vdev beginnt zu resilvern (resilver_start)
  def test_resilver_start(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what== ZFSOperationState.RESILVERING)

  # vdev resilver ist abgeschlossen (resilver_finish)
  def test_resilver_finish(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what == ZFSOperationState.NONE)

  # # zmirror started scrub
  # pool scrub startet (scrub_start)
  def test_scrub_start(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what == ZFSOperationState.SCRUBBING)

  # pool scrub ist abgeschlossen (scrub_finish)
  def test_scrub_finish(self):
    trigger_event(inspect.currentframe().f_code.co_name)
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.operation.what == ZFSOperationState.NONE)

  # # tatsächliches gerät wird abgetrennt
  # partition verschwindet (udev: remove)
  def test_partition_remove(self):
    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Partition = zmirror_core.cache_dict[partition_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())

  # disk verschwindet (udev: remove)
  def test_disk_remove(self):
    trigger_event(inspect.currentframe().f_code.co_name)

    dev: Disk = zmirror_core.cache_dict[disk_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())

  # # zmirror command: zpool offline vdev
  # vdev wird faulted (falls der zmirror command nich schneller ist)
  # vdev wird disconnected (falls der zmirror command nich schneller ist... außerdem kann es sein, dass alex sich irrt und disconnected gibt es nicht im zfs speak) 
  # vdev wird offline (weil zmirror den command geschickt hat)


  def test_zdev_disconnected(self):
    assert zfs_blockdev_id in zmirror_core.cache_dict
    
    trigger_event(inspect.currentframe().f_code.co_name)

    dev: ZFSBackingBlockDevice = zmirror_core.cache_dict[zfs_blockdev_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())

  # virtual disk taucht auf (udev: add)
  def test_virtual_disk_add(self):
    
    zmirror_core.cache_dict = dict()
    assert virtual_disk_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    assert virtual_disk_id in zmirror_core.cache_dict
    
    dev: VirtualDisk = zmirror_core.cache_dict[virtual_disk_id]
    
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

  # virtual disk verschwindet (udev: remove)
  def test_virtual_disk_remove(self):
    
    assert virtual_disk_id in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: VirtualDisk = zmirror_core.cache_dict[virtual_disk_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())

  # logical volume taucht auf (udev: add)
  def test_logical_volume_add(self):
    
    zmirror_core.cache_dict = dict()
    assert logical_volume_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)
    
    assert logical_volume_id in zmirror_core.cache_dict

    dev: LVMLogicalVolume = zmirror_core.cache_dict[logical_volume_id]
    
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

  # logical volume verschwindet (udev: remove)
  def test_logical_volume_remove(self):
    
    assert logical_volume_id in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: LVMLogicalVolume = zmirror_core.cache_dict[logical_volume_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online != None)
    assert(dev.last_online < datetime.now())


  # zfs_volume taucht auf (udev: add)
  def test_zfs_volume_add(self):
    
    zmirror_core.cache_dict = dict()
    assert zfs_volume_id not in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    assert zfs_volume_id in zmirror_core.cache_dict
    
    dev: ZFSVolume = zmirror_core.cache_dict[zfs_volume_id]
    
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.ONLINE)

  # zfs_volume verschwindet (udev: remove)
  def test_zfs_volume_remove(self):
    
    assert zfs_volume_id in zmirror_core.cache_dict

    trigger_event(inspect.currentframe().f_code.co_name)

    dev: ZFSVolume = zmirror_core.cache_dict[zfs_volume_id]
    
    assert(dev is not None)
    assert(dev.state.what == EntityState.DISCONNECTED)
    assert(dev.last_online is not None)
    assert(dev.last_online < datetime.now())
    
    # process.kill()

if __name__ == '__main__':
    if False:
        test_methods = Test_Group1_TestMethods()
        test_methods.test_some_test1()
    else:
        pytest.main()