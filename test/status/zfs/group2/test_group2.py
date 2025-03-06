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
import os
import json
import inspect
from datetime import datetime
import pytest
import zmirror_commands
from zmirror_dataclasses import EntityState, ZFSBackingBlockDeviceCache, ZFSOperationState, ZFSBackingBlockDevice, ZFSVolume, Disk, Partition

import zmirror_utils as zmirror_core
from zmirror_daemon import handle
from zmirror import myexec, scrub
from pyutils import load_yaml_cache


pyexec = exec
exec = myexec #pylint: disable=redefined-builtin



ZFS_BLOCKDEV_ID = "ZFSBackingBlockDeviceCache|zpool-a|partition-a"
PARTITION_ID = "Partition|partition-a"
DM_ID= "DM_Crypt|dm-alpha"
DISK_ID = "Disk|0123456789abcdef"
ZPOOL_ID = "ZPool|zpool-a"
VIRTUAL_DISK_ID = "VirtualDisk|0123456789abcdef"
ZFS_VOLUME_ID = "ZFSVolume|zpool-a|path/zfs-volume"
LOGICAL_VOLUME_ID = "LVMLogicalVolume|vg-alpha|lv-1"



def open_local(file, mode):
  filepath = os.path.join(os.path.dirname(__file__), file)
  return open(filepath, mode, encoding='utf-8')

def get_zpool_status_stub(args): #pylint: disable=unused-argument
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

def do_nothing(*args): #pylint: disable=unused-argument
  pass

def load_dummy_cache(**args): #pylint: disable=unused-argument
  zmirror_core.cache_dict = load_yaml_cache("./test/status/zfs/group2/test_cache.yml")


zmirror_core.load_cache = load_dummy_cache
zmirror_core.write_cache = do_nothing

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


  def setup_method(self, method): #pylint: disable=unused-argument
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


  def teardown_method(self, method): #pylint: disable=unused-argument
    # terminate_thread(self.daemon_thread)
    # silent_remove(core.cache_file_path)
    # pass
    zmirror_commands.commands = []



  # # tatsächliches gerät wird angeschlossen

  # disk taucht auf (udev: add)
  def test_disk_zmirror_sysfs_a_online(self):
    trigger_event()
    # zmirror needs to do nothing (issue no commands)


  # partition taucht auf (udev: add)
  def test_partition_zmirror_sysfs_a_online(self):
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


  #zpool export zmirror-sysfs
  #zpool import zmirror-sysfs
  def test_zpool_zmirror_sysfs_online(self):
    trigger_event()
    

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
      "zfs snapshot zmirror-bak-a/sysfs@timestamp"# TODO:
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
    assert ZFS_BLOCKDEV_ID not in zmirror_core.cache_dict
    trigger_event()
    assert ZFS_BLOCKDEV_ID in zmirror_core.cache_dict
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[ZFS_BLOCKDEV_ID]
    assert dev is not None
    assert dev.state.what == EntityState.ONLINE


  # vdev beginnt zu resilvern (resilver_start)
  def test_resilver_start(self):
    trigger_event()
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[ZFS_BLOCKDEV_ID]
    assert dev is not None
    assert dev.operation.what== ZFSOperationState.RESILVERING

  # vdev resilver ist abgeschlossen (resilver_finish)
  def test_resilver_finish(self):
    trigger_event()
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[ZFS_BLOCKDEV_ID]
    assert dev is not None
    assert dev.operation.what == ZFSOperationState.NONE

  # # zmirror started scrub
  # pool scrub startet (scrub_start)
  def test_scrub_start(self):
    trigger_event()
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[ZFS_BLOCKDEV_ID]
    assert dev is not None
    assert dev.operation.what == ZFSOperationState.SCRUBBING

  # pool scrub ist abgeschlossen (scrub_finish)
  def test_scrub_finish(self):
    trigger_event()
    dev: ZFSBackingBlockDeviceCache = zmirror_core.cache_dict[ZFS_BLOCKDEV_ID]
    assert dev is not None
    assert dev.operation.what == ZFSOperationState.NONE

  # # tatsächliches gerät wird abgetrennt
  # partition verschwindet (udev: remove)
  def test_partition_remove(self):
    trigger_event()
    dev: Partition = zmirror_core.cache_dict[PARTITION_ID]
    assert dev is not None
    assert dev.state.what == EntityState.DISCONNECTED
    assert dev.last_online is not None
    assert dev.last_online < datetime.now()

  # disk verschwindet (udev: remove)
  def test_disk_remove(self):
    trigger_event()
    dev: Disk = zmirror_core.cache_dict[DISK_ID]
    assert dev is not None
    assert dev.state.what == EntityState.DISCONNECTED
    assert dev.last_online is not None
    assert dev.last_online < datetime.now()

  # # zmirror command: zpool offline vdev
  # vdev wird faulted (falls der zmirror command nich schneller ist)
  # vdev wird disconnected (falls der zmirror command nich schneller ist... außerdem kann es sein, dass alex sich irrt und disconnected gibt es nicht im zfs speak)
  # vdev wird offline (weil zmirror den command geschickt hat)


  def test_zdev_disconnected(self):
    assert ZFS_BLOCKDEV_ID in zmirror_core.cache_dict
    trigger_event()
    dev: ZFSBackingBlockDevice = zmirror_core.cache_dict[ZFS_BLOCKDEV_ID]
    assert dev is not None
    assert dev.state.what == EntityState.DISCONNECTED
    assert dev.last_online is not None
    assert dev.last_online < datetime.now()

  # zfs_volume taucht auf (udev: add)
  def test_zfs_volume_add(self):
    zmirror_core.cache_dict = dict()
    assert ZFS_VOLUME_ID not in zmirror_core.cache_dict

    trigger_event()
    assert ZFS_VOLUME_ID in zmirror_core.cache_dict
    dev: ZFSVolume = zmirror_core.cache_dict[ZFS_VOLUME_ID]
    assert dev is not None
    assert dev.state.what == EntityState.ONLINE

  # zfs_volume verschwindet (udev: remove)
  def test_zfs_volume_remove(self):
    assert ZFS_VOLUME_ID in zmirror_core.cache_dict

    trigger_event()

    dev: ZFSVolume = zmirror_core.cache_dict[ZFS_VOLUME_ID]
    assert dev is not None
    assert dev.state.what == EntityState.DISCONNECTED
    assert dev.last_online is not None
    assert dev.last_online < datetime.now()
    # process.kill()

if __name__ == '__main__':
  pytest.main()
