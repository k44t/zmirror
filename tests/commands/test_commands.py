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
import re


from util.util_stage1 import *



from zmirror.daemon import handle
import zmirror.commands
from zmirror.dataclasses import *
import zmirror.config
from zmirror.zmirror import scrub
import zmirror.entities as entities
from zmirror.zmirror import main
import zmirror.operations as operations

from util.util_stage2 import *





@pytest.fixture(scope="class", autouse=True)
def setup_before_all_methods():
  # Code to execute once before all test methods in each class
  insert_zpool_status_stub()
  prepare_config_and_cache()


# zmirror_core.load_cache = load_dummy_cache
# zmirror_core.write_cache = do_nothing

def assert_commands(cmds):
  return 
  assert (
      cmds == commands.commands
  )

# this group of tests all require the daemon running, hence they are grouped
class TestExampleConfig():


  # event_queue = None
  @classmethod
  def setup_class(cls):
    entities.init_config(config_path="./example-config.yml", cache_path="./tests/commands/test_cache.yml")


  def setup_method(self, method): #pylint: disable=unused-argument
    pass
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
    commands.commands = []


  # #####################
  # sysfs
  # #####################


  # sysfs-a
  # #####################


  # physical device of sysfs-a gets plugged-in (by user)
  # disk of sysfs-a appears (udev: add)
  def test_disk_sysfs_a_online(self):

    # the disk is not part of the configuration, but zmirror should still update its cache
    trigger_event()


    # zmirror needs to do nothing (issue no commands)
    assert_commands([])


  # partition of sysfs-a appears (udev: add)
  def test_partition_sysfs_a_online(self):

    trigger_event()
    
    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-a zmirror-sysfs-a --key_file ./test/zmirror-key"
    ])


  # dmcrypt of sysfs-a appears
  def test_dmcrypt_sysfs_a_online(self):

    trigger_event()

    assert_commands([
      # zmirror should not import the zmirror-sysfs pool
      ## "zpool import zmirror-sysfs",

      # but it should try to online the device, which in this case should 
      # not succeed, since the pool is not imported yet
      "zpool online zmirror-sysfs zmirror-sysfs-a"
    ])

  # `zpool import zmirror-sysfs-a` (do `zpool export zmirror-sysfs-a` before, if the pool is already imported)
  def test_zpool_sysfs_online(self):
    trigger_event()

    # zmirror has to do nothing
    assert_commands([])


  # sysfs-b
  # ###############


  # physical device of sysfs-b gets plugged-in
  # disk of sysfs-b appears (udev: add)
  def test_disk_sysfs_b_online(self):
    trigger_event()

    # zmirror needs to do nothing (issue no commands)
    assert_commands([])

  # partition of sysfs-b appears (udev: add)
  def test_partition_sysfs_b_online(self):
    trigger_event()

    assert_commands([

      # open the dm_crypt inside the partition
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-b zmirror-sysfs-b --key_file ./test/zmirror-key"

    ])

  # dmcrypt of sysfs-b appears
  def test_dmcrypt_sysfs_b_online(self):
    trigger_event()

    assert_commands([
      "zpool online zmirror-sysfs zmirror-sysfs-b"
    ])

  # the event when the blockdev actually goes online inside the zpool
  def test_backing_blockdev_sysfs_b_online(self):
    trigger_event()

    # zmirror needs to do nothing (issue no commands)
    assert_commands([])

  # resilvering starts
  def test_zpool_sysfs_backing_blockdev_sysfs_b_resilver_start(self):
    trigger_event()

    # zmirror needs to do nothing (issue no commands)
    assert_commands([])

  # resilvering ends
  def test_zpool_sysfs_backing_blockdev_sysfs_b_resilver_finish(self):
    trigger_event()

    # zmirror needs to do nothing (issue no commands) as nothing is defined in the config file
    assert_commands([])


  def test_trigger_scrub_sysfs_a_and_b(self):
    
    operations.scrub_all_overdue()

    assert_commands([
      "zpool scrub zmirror-sysfs"
    ])


  # scrub start
  def test_scrub_started_sysfs_a_and_b(self):
    
    trigger_event()

    assert_commands([])


  # scrub finished
  def test_scrub_finished_sysfs_a_and_b(self):

    trigger_event()

    assert_commands([])



  # sysfs-s
  # ###################


  # physical device of sysfs-s gets plugged-in
  # disk of sysfs-s appears (udev: add)
  def test_disk_sysfs_s_online(self):

    trigger_event()

    # zmirror needs to do nothing (issue no commands)
    assert_commands([])

  # partition of sysfs-s appears (udev: add)
  def test_partition_sysfs_s_online(self):
    
    trigger_event()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key_file ./test/zmirror-key"
    ])

  # dmcrypt of sysfs-s appears
  def test_dmcrypt_sysfs_s_online(self):
    
    trigger_event()
    
    assert_commands([
      "zpool online zmirror-sysfs zmirror-sysfs-s"
    ])

  # the event when the blockdev actually goes online inside the zpool
  def test_backing_blockdev_sysfs_s_online(self):
    
    trigger_event()
    
    assert_commands([])


  def test_zpool_sysfs_backing_blockdev_sysfs_s_resilver_start(self):
    trigger_event()
    
    assert_commands([])


  def test_zpool_sysfs_backing_blockdev_sysfs_s_resilver_finish(self):
    trigger_event()
    
    # zmirror needs to do nothing (issue no commands) as nothing is defined in the config file
    assert_commands([])




  # ###################
  # big
  # ###################


  # big-b
  # ###############

  # we do zmirror-big-b first, because zmirror should only
  # import the pool once the required disk zmirror-big-a is also present.

  # physical device of big-b gets plugged-in
  # disk of big-b appears (udev: add)
  def test_disk_big_b_online(self):
    trigger_event()

    # zmirror needs to do nothing (issue no commands)
    assert_commands([])

  # partition of big-b appears (udev: add)
  def test_partition_big_b_online(self):
    trigger_event()

    assert_commands([

      # open the dm_crypt inside the partition
      "cryptsetup open /dev/disk/by-partlabel/zmirror-big-b zmirror-big-b --key_file ./test/zmirror-key"

    ])

  # dmcrypt of big-b appears
  def test_dmcrypt_big_b_online(self):
    trigger_event()

    assert_commands([
      # this command will fail as the pool is not yet imported
      "zpool online zmirror-big zmirror-big-b"
    ])


  # big-a
  # ##############


  # physical device of big-a gets plugged-in (by user)
  # disk of big-a appears (udev: add)
  def test_disk_big_a_online(self):

    # the disk is not part of the configuration, but zmirror should still update its cache
    trigger_event()


    # zmirror needs to do nothing (issue no commands)
    assert_commands([])


  # partition of big-a appears (udev: add)
  def test_partition_big_a_online(self):

    trigger_event()
    
    assert_commands([
      # now the zpool should be imported
      "cryptsetup open /dev/disk/by-partlabel/zmirror-big-a zmirror-big-a --key_file ./test/zmirror-key"
    ])


  # dmcrypt of big-a appears
  def test_dmcrypt_big_a_online(self):

    trigger_event()

    assert_commands([
      # now zmirror should import the zmirror-big pool
      "zpool import zmirror-big",

      # whether the pool is already imported or not
      # the online command is always issued (if required by the configuration)
      "zpool online zmirror-big zmirror-big-a"
    ])



  # #########################################
  # bak-a
  # #########################################

  
  # physical device of bak-a gets plugged-in
  # disk of bak-a appears (udev: add)
  def test_disk_bak_a_online(self):

    trigger_event()

    assert_commands([])


  # partition of bak-a appears (udev: add)
  def test_partition_bak_a_online(self):

    trigger_event()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-bak-a zmirror-bak-a --key_file ./test/zmirror-key"
    ])



  # when dmcrypt of bak-a appears
  def test_dmcrypt_bak_a_online(self):
    
    trigger_event()
    
    assert_commands([
      # we import the bak-a pool
      "zpool import zmirror-bak-a"
    ])

  def test_zpool_bak_a_online(self):
    trigger_event()

    # zpool is configured to take the volumes "online"
    # and we have implemented this by setting the volmode
    # so that the respective udev events will be triggered
    # which then we process (in the next tests).
    assert_commands([
      "zfs set volmode=full zmirror-bak-a/sysfs"
      "zfs set volmode=full zmirror-bak-a/big"
    ])

  # when bak-a-sysfs zfs_volume appears (udev: add)
  def test_zfs_volume_bak_a_sysfs_online(self):
    trigger_event()
    assert_commands([
      "zpool online zmirror-sysfs zvol/zmirror-bak-a/sysfs"
    ])

  # when bak-a-big zfs_volume appears (udev: add)
  def test_zfs_volume_bak_a_big_online(self):
    trigger_event()

    assert_commands([
      # we online the blockdev
      "zpool online zmirror-big zvol/mirror-bak-a/big"
    ])


  # when the resilver starts
  def test_zpool_sysfs_backing_blockdev_bak_a_sysfs_resilver_start(self):
    trigger_event()
    # zmirror needs to do nothing (issue no commands)
    assert_commands([])


  # when the resilver has finished
  def test_zpool_big_backing_blockdev_bak_a_big_resilver_start(self):
    trigger_event()
    # zmirror needs to do nothing (issue no commands)
    assert_commands([])



  # when the resilver on the zvols/zmirror-bak-a/sysfs blockdev finishes...
  def test_zpool_sysfs_backing_blockdev_bak_a_sysfs_resilver_finish(self):
    trigger_event()

    assert_commands([
      # we make a snapshot of the volume that backs it
      re.compile(r"zfs snapshot zmirror-bak-a/sysfs@.*"),

      # and then we take it offline.
      #
      # It must be in this order
      # for zmirror to be able to react to the udev events
      # apropriately.
      "zpool offline zmirror-sysfs zvol/zmirror-bak-a/sysfs"
    ])



  # when the blockdev is taken offline within the sysfs pool
  def test_zpool_sysfs_backing_blockdev_bak_a_sysfs_disconnected(self):
    trigger_event()

    # we virtually take our volume offline as well (setting volmode=none)
    assert_commands([
      "zfs set volmode=none zmirror-bak-a/sysfs"
    ])


  # when then the event arrives we just triggered by taking setting volmode=none
  def test_zfs_volume_bak_a_sysfs_offline(self):
    
    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the resilver of zvol/zmirror-bak-a/big finishes
  def test_zpool_big_backing_blockdev_bak_a_big_resilver_finish(self):
    
    trigger_event()

    assert_commands([
      # we make a snapshot of the volume that backs it
      re.compile(r"zfs snapshot zmirror-bak-a/big@.+"),

      # and then we take it offline.
      #
      # It must be in this order
      # for zmirror to be able to react to the udev events
      # apropriately.
      "zpool offline zmirror-big zvol/zmirror-bak-a/big"
    ])

  # when the blockdev is being taken offline in the big pool
  def test_zpool_big_backing_blockdev_bak_a_big_disconnected(self):
    trigger_event()
    assert_commands([
      # we virtually take our volume offline as well (setting volmode=none)
      "zfs set volmode=none zmirror-bak-a/big"
    ])

  # when then the event arrives we just triggered by taking setting volmode=none
  def test_zfs_volume_bak_a_big_offline(self):
    trigger_event()
    
    assert_commands([
      # now both sysfs and big are offline, therefore we can offline the whole bak pool
      "zpool export zmirror-bak-a"
    ])

  # when the offline event comes
  def test_zpool_bak_a_offline(self):

    # this generates virtual events (that means the handle_ methods will be called)
    # on all the backing blockdevs of that pool that were online.
    trigger_event()

    assert_commands([
      # we close the encrypted device
      "cryptsetup close zmirror-bak-a"
    ])

  # when the encrypted device disappears
  def test_dmcrypt_bak_a_offline(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])




  # #########################################
  # bak-b
  # #########################################
  
  
  # bak-b-alpha
  # ###################

  # physical device of bak-b-alpha gets plugged-in
  
  # when the disk of bak-b-alpha appears (udev: add)
  def test_disk_bak_b_alpha_online(self):
    
    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when partition of bak-b-alpha appears (udev: add)
  def test_partition_bak_b_alpha_online(self):
    
    trigger_event()
    
    assert_commands([
      # we open the encrypted device
      "cryptsetup open /dev/disk/by-partlabel/zmirror-bak-b-alpha zmirror-bak-b-alpha --key_file ./test/zmirror-key"
    ])


  # when the dmcrypt of bak-b-alpha appears
  def test_dmcrypt_bak_b_alpha_online(self):

    trigger_event()

    assert_commands([
      # and since this command can safely be run
      # whether the pool is online or not
      # (without triggering any event in case the device was already online)
      # we simply issue it here
      "zpool online zmirror-bak-b zmirror-bak-b-alpha"
    ])


  # bak-b-beta
  # ###################



  # physical device of bak-b-alpha gets plugged-in
  # when disk of bak-b-alpha appears (udev: add)
  def test_disk_bak_b_beta_online(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when partition of bak-b-alpha appears (udev: add)
  def test_partition_bak_b_beta_online(self):
    
    trigger_event()

    assert_commands([

      # we decrypt
      "cryptsetup open /dev/disk/by-partlabel/zmirror-bak-b-alpha zmirror-bak-b-alpha --key_file ./test/zmirror-key"
    ])


  # when dmcrypt of bak-b-alpha appears
  def test_dmcrypt_bak_b_beta_online(self):
    trigger_event()

    assert_commands([
      # we import because now all required backing disks are present
      "zpool import zmirror-bak-b"

      # we always issue the online command, in case it is configured (which it is in this case)
      "zpool online zmirror-bak-b zmirror-bak-b-beta"
    ])


  # when the pool comes online
  def test_zpool_bak_b_online(self):
    trigger_event()

    assert_commands([
      # zmirror virtually takes the volumes "online"
      "zfs set volmode=full zmirror-bak-b/sysfs"
      "zfs set volmode=full zmirror-bak-b/big"
    ])

  # when bak-b-sysfs zfs_volume appears (udev: add) (caused by set volmode=full)
  def test_zfs_volume_bak_b_sysfs_online(self):
    
    trigger_event()
    
    assert_commands([
      # we online it in the sysfs pool
      "zpool online zmirror-sysfs zvol/zmirror-bak-b/sysfs"
    ])

  # when bak-b-big zfs_volume appears (udev: add)
  def test_zfs_volume_bak_b_big_online(self):
    
    trigger_event()
    
    assert_commands([

      # we online it in the sysfs pool big pool
      "zpool online zmirror-big zvol/mirror-bak-b/big"
    ])


  # when the resilver of the volume for sysfs starts
  def test_zpool_sysfs_backing_blockdev_bak_b_sysfs_resilver_start(self):
    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the resilver of the volume for big starts
  def test_zpool_big_backing_blockdev_bak_b_big_resilver_start(self):
    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the resilver for sysfs finishes
  def test_zpool_sysfs_backing_blockdev_bak_b_sysfs_resilver_finish(self):
    trigger_event()
    assert_commands([
      
      
      # we make a snapshot of the volume that backs it
      re.compile(r"zfs snapshot zmirror-bak-b/sysfs@.+"),

      
      # and then we take it offline.
      "zpool offline zmirror-sysfs zvol/zmirror-bak-b/sysfs"
    ])


  # when it the event from taking it offline in the pool appears
  def test_zpool_sysfs_backing_blockdev_bak_b_sysfs_disconnected(self):
    trigger_event()
    assert_commands([
      
      # we also virtually take the volume "offline" in which it resides
      "zfs set volmode=none zmirror-bak-b/sysfs"
    ])



  # when the event we just caused makes the volume disappear
  def test_zfs_volume_bak_b_sysfs_offline(self):
    trigger_event()

    assert_commands([
      # we do nothing
    ])

  # when the resilver for big finishes
  def test_zpool_big_backing_blockdev_bak_b_big_resilver_finish(self):
    trigger_event()

    assert_commands([
      # we make a snapshot of the volume that backs it
      re.compile(r"zfs snapshot zmirror-bak-b/big@.+"),

      # and then we take it offline.
      "zpool offline zmirror-big zvol/zmirror-bak-b/big"
    ])

  # when the blockdev disappears from the pool it backs
  def test_zpool_big_backing_blockdev_bak_b_big_disconnected(self):
    trigger_event()
    assert_commands([
      # we also virtually take the volume "offline" in which it resides
      "zfs set volmode=none zmirror-bak-b/big"
    ])

  # when the volume disappears
  def test_zfs_volume_bak_b_big_offline(self):
    trigger_event()
    
    assert_commands([

      # now both sysfs and big are offline, therefore we take the whole pool offline
      "zpool export zmirror-bak-b"
    ])

  # when the pool goes offline
  def test_zpool_bak_b_offline(self):

    # zmirror realizes that the backing blockdevs are now offline
    trigger_event()

    assert_commands([
      # and so the encrypted disks in which they reside are also taken offline
      "cryptsetup close zmirror-bak-b-alpha"
      "cryptsetup close zmirror-bak-b-beta"
    ])

  # when the first encrypted disk is closed
  def test_dmcrypt_bak_b_alpha_offline(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the second encrypted disk is closed
  def test_dmcrypt_bak_b_beta_offline(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the first physical disk is being unplugged
  def test_disk_bak_b_alpha_offline(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])

  # when the partition inside it disappears (this event always happens after the disk event)
  def test_partition_bak_b_alpha_offline(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the second physical disk is being unplugged
  def test_disk_bak_b_beta_offline(self):

    trigger_event()

    assert_commands([
      # we do nothing
    ])


  # when the partition inside it disappears (this event always happens after the disk event)
  def test_partition_bak_b_beta_offline(self):

    trigger_event()


    assert_commands([
      # we do nothing
    ])




if __name__ == '__main__':
  pytest.main()
