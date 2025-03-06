#!/bin/python3
# ******************************************************************************
# - *-coding: utf-8 -*-
# (c) copyright 2025 Alexander Poeschl
# All rights reserved.
# ******************************************************************************
# @file test_group2.py
# @author Alexander Poeschl <apoeschlfreelancing@kwanta.net>, Michael Poeschl
# @brief Pytests group2 for zmirror
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



def trigger_event():
  name = inspect.currentframe().f_back.f_code.co_name
  event = load_event(name + ".json")
  handle(event)

def load_event(json_file):
  with open_local(json_file, "r") as f:
    src = f.read()
  return json.loads(src)
#     self.event_queue.put(event)

def do_nothing(*args):
  pass

def load_dummy_cache(*args):
  zmirror_utils.cache_dict = load_yaml_cache("./test/status/zfs/group2/test_cache.yml")


zmirror_utils.load_cache = load_dummy_cache
zmirror_utils.write_cache = do_nothing

def assert_commands(cmds): 
  assert (
      cmds == zmirror_commands.commands
  )

# this group of tests all require the daemon running, hence they are grouped
class TestExampleConfig():


  # event_queue = None
  @classmethod
  def setup_class(cls):
    zmirror_core.load_config(config_path="./example-config.yml")
    zmirror_core.load_cache(cache_path="./test/cache.yml")


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
  def test_disk_online(self):


    trigger_event()

    # zmirror needs to do nothing (issue no commands)


  # partition taucht auf (udev: add)
  def test_partition_online(self):
    

    trigger_event()


    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-a zmirror-sysfs-a --key_file ./test/zmirror-key"
    ])





  def test_dmcrypt_zmirror_sysfs_a_online(self):
    trigger_event()

    assert_commands([
      "zpool import zmirror-sysfs",
      "zpool online zmirror-sysfs zmirror-sysfs-a"
    ])
  

  def test_zpool_sysfs_online(self):
    pass

  # sysfs-b: dmcrypts partition und so

  def test_zpool_sysfs_backing_blockdev_sysfs_b_online(self):
    pass

  def test_zpool_sysfs_backing_blockdev_sysfs_b_resilver_start(self):
    pass
  
  def test_zpool_sysfs_backing_blockdev_sysfs_b_resilver_finish(self):
    pass
  


    # TODO: implement scheduler: */*/14 03:00
    # TODO: implement cache file path configurable (and different path when testing)
    # TODO: implement scrubbing interval
  
  def test_trigger_scrub(self):
    scrub(None)
    assert_commands([
      "zpool scrub zmirror-sysfs"
    ])

  def scrub_started(self):
    pass

  def scrub_finished(self):
    pass

  # bak-a sysfs
  def resilver_finished(self):
    assert_commands([
      "zpool offline zmirror-sysfs zvol/zmirror-bak-a/sysfs"
    ])
  
  def zpool_sysfs_bak_a_backing_zvol_offline(self):
    assert_commands([
      "zfs snapshot zmirror-bak-a/sysfs@timestamp"#TODO
      # this command only works once the inner device has actually been taken offline (no longer in use), or else the blockdev will just remain available as linux tracks usage...
      "zfs set volmode=none zmirror-bak-a/sysfs"
    ])

  def zvol_offline_event(self):
    pass

  
  def big_zvol_offline_event(self):
    assert_commands([
      "zpool export zmirror-bak-a"
    ])
  
  def zpool_zmirror_bak_a_is_offline(self):
    # at this point the zmirror-bak-a ZFSBackingBlockDevice must be considered offline. i.e. the pool export event should trigger an offline event on each backingblockdev if we implemented this correctly
    assert_commands([
      "cryptsetup close zmirror-bak-a"
    ])

  def dmcrypt_has_been_offline(self):
    pass
  


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