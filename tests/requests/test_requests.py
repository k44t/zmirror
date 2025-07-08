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
import tempfile

from itertools import zip_longest

from util.util_stage1 import *



import zmirror.commands
from zmirror.dataclasses import *
import zmirror.config
import zmirror.entities as entities
from zmirror.zmirror import main

from util.util_stage2 import *

import zmirror.user_commands as user_commands




@pytest.fixture(scope="class", autouse=True)
def setup_before_all_methods():
  # Code to execute once before all test methods in each class
  insert_zpool_status_stub()
  insert_dev_exists_stub()
  insert_get_zfs_volume_mode_stub()
  insert_find_provisioning_mode_stub()




# in this test, some of the disks required to import some of the pools are present
# we test the request capability of onlining target devices by onlining all their
# dependency hierarchy. To be able to test this we take example-config and remove
# all `online` actions.
class Tests():


  @classmethod
  def setup_class(cls):


    

    with open('./example-config.yml', 'r') as file:
      content = file.read()



    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
      
      
      # Apply the regex substitution
      content = re.sub(r"- online(?=\s|$)", "- pass", content)

      temp_file.write(content.encode("utf-8"))

      temp_file.close()

      entities.init_config(config_path=temp_file.name, cache_path="./tests/commands/test_cache.yml")


    for entity in config.cache_dict.values():
      assert entity.state.what == EntityState.DISCONNECTED


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
    trigger_event()


  # partition of sysfs-a appears (udev: add)
  def test_partition_sysfs_a_online(self):
    trigger_event()


  # sysfs-b
  # #####################

  # physical device of sysfs-b gets plugged-in
  # disk of sysfs-b appears (udev: add)
  def test_disk_sysfs_b_online(self):
    trigger_event()


  # partition of sysfs-b appears (udev: add)
  def test_partition_sysfs_b_online(self):
    trigger_event()



  # sysfs-s
  # #####################

  def test_request_zpool_sysfs_s_online(self):

    user_commands.request(RequestType.ONLINE_IF_POOL, ZDev, pool="zmirror-sysfs", name="zmirror-sysfs-s")

    dmcrypt = config.cache_dict["DMCrypt|name:zmirror-sysfs-s"]

    # the requests should not be in there, because they must have failed since the partition
    # could not have been onlined.
    assert RequestType.ONLINE not in dmcrypt.requested and RequestType.ONLINE_IF_POOL not in dmcrypt.requested

    assert_commands([
      # nothing should happen as zmirror-sysfs is not available yet
    ])


  # partition of sysfs-s appears (udev: add)... 
  # this is to test udev events appearing in a weird order (partition before disk)
  def test_partition_sysfs_s_online(self):
    trigger_event()
 
    assert_commands([
      'echo unmap > /#/projects/zmirror/tests/requests/res/provisioning_mode.txt',
      
      # this should not happen, as the request should have already failed
      ##  'cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key'
    ])


  # physical device of sysfs-s gets plugged-in (by user)
  # disk of sysfs-a appears (udev: add)
  def test_disk_sysfs_s_online(self):
    trigger_event()


    assert_commands([
      # nothing should happen
    ])


  def test_request_zpool_sysfs_b_online(self):

    partition = config.cache_dict["Partition|name:zmirror-sysfs-b"]
    dmcrypt = config.cache_dict["DMCrypt|name:zmirror-sysfs-b"]

    assert partition.state.what == EntityState.ONLINE
    assert dmcrypt.state.what == EntityState.INACTIVE

    dmcrypt_entity = config.config_dict["DMCrypt|name:zmirror-bak-a"]

    assert not dmcrypt_entity.requested

    user_commands.request(RequestType.ONLINE, ZDev, pool="zmirror-sysfs", name="zmirror-sysfs-b")



    # the online request for bak-a should have failed and hence nothing should
    # currently be requested
    assert not dmcrypt_entity.requested

    # all present disks that make part of the zpool should be decrypted
    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-b zmirror-sysfs-b --key-file ./test/zmirror-key",
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-a zmirror-sysfs-a --key-file ./test/zmirror-key",
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key",
    ])





  # dmcrypt of sysfs-a appears
  def test_dmcrypt_sysfs_a_online(self):

    pool = config.config_dict["ZPool|name:zmirror-sysfs"]

    dmcrypt_a = config.config_dict["DMCrypt|name:zmirror-sysfs-a"]


    zdev_a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]


    assert RequestType.ONLINE in dmcrypt_a.requested

    dmcrypt_request = dmcrypt_a.requested[RequestType.ONLINE]

    assert not dmcrypt_request.handled
    assert not dmcrypt_request.succeeded


    assert RequestType.APPEAR in zdev_a.requested

    zdev_request = zdev_a.requested[RequestType.APPEAR]

    assert RequestType.ONLINE in pool.requested

    assert not zdev_request.handled
    assert not zdev_request.succeeded

    trigger_event()


    assert dmcrypt_request.handled
    assert dmcrypt_request.succeeded

    assert zdev_request.handled
    assert zdev_request.succeeded

    assert RequestType.ONLINE in pool.requested


    assert_commands([
      # at this point no command should be issued, because zmirror is supposed to wait for
      # all dependencies (all zdevs) to either either fulfil or fail their appear requests. 
      # Hence we must trigger the appear events now.
      ## "zpool import zmirror-sysfs",

      # the zpool insn't online yet, so the online command is not being issued
      ## "zpool online zmirror-sysfs zmirror-sysfs-a"
    ])








  # dmcrypt of sysfs-b appears
  def test_dmcrypt_sysfs_b_online(self):
    trigger_event()

    assert_commands([
      ## "zpool online zmirror-sysfs zmirror-sysfs-b"
    ])



  # dmcrypt of sysfs-b appears
  def test_dmcrypt_sysfs_s_online(self):

    pool = config.config_dict["ZPool|name:zmirror-sysfs"]

    zdev_a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    zdev_b = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    zdev_s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]


    assert RequestType.ONLINE in pool.requested

    request = pool.requested[RequestType.ONLINE]
    

    assert RequestType.ONLINE in zdev_a.requested

    # has already appeared
    assert RequestType.APPEAR not in zdev_a.requested


    # ONLINE has been requested manually for zdev_b
    assert RequestType.ONLINE in zdev_b.requested
    
    # has already appeared
    assert RequestType.APPEAR not in zdev_b.requested


    assert RequestType.ONLINE not in zdev_s.requested
    assert RequestType.APPEAR in zdev_s.requested



    trigger_event()

    assert_commands([
      "zpool import zmirror-sysfs"
    ])


  # `zpool import zmirror-sysfs-a` (do `zpool export zmirror-sysfs-a` before, if the pool is already imported)
  def test_zpool_sysfs_online(self):

    pool = config.cache_dict["ZPool|name:zmirror-sysfs"]


    zdev_a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    zdev_b = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    zdev_s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    trigger_event()

    assert pool.state.what == EntityState.ONLINE



    # zmirror has to do nothing
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





  # #########################################
  # bak-a
  # #########################################

  
  # physical device of bak-a gets plugged-in
  # disk of bak-a appears (udev: add)
  def test_disk_bak_a_online(self):

    dmcrypt_entity = config.config_dict["DMCrypt|name:zmirror-bak-a"]

    assert not dmcrypt_entity.requested

    trigger_event()

    assert not dmcrypt_entity.requested

    assert_commands([])


  # partition of bak-a appears (udev: add)
  def test_partition_bak_a_online(self):

    dmcrypt_entity = config.config_dict["DMCrypt|name:zmirror-bak-a"]

    assert not dmcrypt_entity.requested

    trigger_event()

    assert_commands([
      # nothing should happen, because we changed the contents of `example-config` to not contain any online handlers
    ])




  def test_request_scrub_zmirror_sysfs(self):
    

    def possibly_scrub(entity):
      if isinstance(entity, ZDev) and entity.pool == "zmirror-sysfs":
        entity.request(RequestType.SCRUB)
    entities.iterate_content_tree(config.config_root, possibly_scrub)
    entities.iterate_content_tree(config.config_root, user_commands.do_enact_requests)

    assert_commands([
      'zpool scrub -s zmirror-sysfs', 
      'zpool scrub zmirror-sysfs', 
      'cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key', 
      'cryptsetup open /dev/disk/by-partlabel/zmirror-bak-a zmirror-bak-a --key-file ./test/zmirror-key'
    ])


  def test_zdev_sysfs_a_scrub_start(self):


    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    
    assert blockdev.operations == []

    trigger_event()

    assert since_in(Operations.SCRUB, blockdev.operations)

    assert_commands([
      
    ])



  # the event when the blockdev actually goes online inside the zpool
  def test_backing_blockdev_sysfs_s_online(self):
    
    trigger_event()

    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    assert since_in(Operations.RESILVER, blockdev.operations)

    
    assert_commands([
      # resilver should start and nothing else happen
    ])


  # the event when the blockdev actually goes online inside the zpool
  def test_zdev_sysfs_s_resilver_finish(self):
    
    trigger_event()

    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    assert not since_in(Operations.RESILVER, blockdev.operations)

    
    assert_commands([
      'zpool scrub -s zmirror-sysfs', 
      'zpool scrub zmirror-sysfs', 
    ])


  def test_zdev_sysfs_s_scrub_start(self):


    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    
    assert blockdev.operations == []

    trigger_event()

    assert since_in(Operations.SCRUB, blockdev.operations)

    assert_commands([
      
    ])


  # when dmcrypt of bak-a appears
  def test_dmcrypt_bak_a_online(self):
    
    trigger_event()
    
    assert_commands([
      # we import the bak-a pool
      "zpool import zmirror-bak-a",

      "zpool online zmirror-bak-a zmirror-bak-a"
    ])


  def test_zpool_bak_a_online(self):

    trigger_event()

    zpool = config.cache_dict["ZPool|name:zmirror-bak-a"]

    blockdev = config.cache_dict["ZDev|pool:zmirror-bak-a|name:zmirror-bak-a"]

    assert blockdev.state.what == EntityState.ONLINE

    # zpool is configured to take the volumes "online"
    # and we have implemented this by setting the volmode
    # so that the respective udev events will be triggered
    # which then we process (in the next tests).
    assert_commands([

      # the volmode for sysfs is set to none (this assuming that zmirror "offlined" the volume safely)
      "zfs set volmode=full zmirror-bak-a/sysfs",

      # big is left alone as it is not requested
      ## "zpool online zmirror-big zvol/zmirror-bak-a/big"
    ])



  # when bak-a-sysfs zfs_volume appears (udev: add)
  def test_zfs_volume_bak_a_sysfs_online(self):

    zpool = config.cache_dict["ZPool|name:zmirror-bak-a"]

    assert zpool.state.what == EntityState.ONLINE

    trigger_event()

    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume = config.cache_dict["ZFSVolume|pool:zmirror-bak-a|name:sysfs"]

    assert_commands([
      "zpool online zmirror-sysfs zvol/zmirror-bak-a/sysfs"
    ])



  # when bak-a-big the blockdev becomes active in the sysfs pool
  def test_zpool_sysfs_backing_blockdev_bak_a_sysfs_online(self):

    bak_a = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]

    req = uncached(bak_a).requested
    assert req == {RequestType.SCRUB, RequestType.ONLINE}

    trigger_event()


    req2 = uncached(bak_a).requested
    
    assert req is req2

    assert req == {RequestType.SCRUB}

    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]

    assert blockdev.state.what == EntityState.ONLINE


    assert_commands([
      # a scrub has been requested and zmirror trys to start it 
      # which will fail because resilvering needs to happen first
      "zpool scrub -s zmirror-sysfs",
      "zpool scrub zmirror-sysfs"
    ])



  # when the resilver starts
  def test_zpool_sysfs_backing_blockdev_bak_a_sysfs_resilver_start(self):
    trigger_event()
    
    assert_commands([])


  # when the resilver ends
  def test_zpool_sysfs_backing_blockdev_bak_a_sysfs_resilver_finish(self):
    trigger_event()
    
    assert_commands([

      "zpool scrub -s zmirror-sysfs",
      "zpool scrub zmirror-sysfs",
      re.compile(r"zfs snapshot zmirror-bak-a/sysfs@.*")
      
      # zmirror refuses to offline the device becausee a scrub is scheduled
      ## 'zpool offline zmirror-sysfs zvol/zmirror-bak-a/sysfs'
    ])



  # scrub start
  def test_scrub_started_sysfs(self):
    
    trigger_event()

    a = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    b = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    bak_a = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    bak_b = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-b/sysfs"]

    assert s.state.what == EntityState.ONLINE

    assert since_in(Operations.SCRUB, a.operations)
    assert since_in(Operations.SCRUB, b.operations)
    assert since_in(Operations.SCRUB, s.operations)
    assert since_in(Operations.SCRUB, bak_a.operations)
    assert not since_in(Operations.SCRUB, bak_b.operations)

    assert_commands([])



  # scrub start
  def test_scrub_finished_sysfs(self):

    a = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    b = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    bak_a = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    bak_b = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-b/sysfs"]

    assert uncached(bak_a).requested == {RequestType.SCRUB}

    trigger_event()



    assert not since_in(Operations.SCRUB, a.operations)
    assert not since_in(Operations.SCRUB, b.operations)
    assert not since_in(Operations.SCRUB, s.operations)
    assert not since_in(Operations.SCRUB, bak_a.operations)
    assert not since_in(Operations.SCRUB, bak_b.operations)

    assert s.state.what == EntityState.ONLINE

    assert_commands([
      "zpool trim zmirror-sysfs zmirror-sysfs-a",
      "zpool trim zmirror-sysfs zmirror-sysfs-b",
      "zpool trim zmirror-sysfs zmirror-sysfs-s",
      "zpool offline zmirror-sysfs zvol/zmirror-bak-a/sysfs"
    ])
  
  def test_zpool_sysfs_backing_blockdev_sysfs_s_trim_start(self):
    
    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    assert s.state.what == EntityState.ONLINE


    trigger_event()

    assert s.state.what == EntityState.ONLINE

    assert since_in(Operations.TRIM, s.operations)

    assert_commands([
    ])


  # an administrator has stopped the trim via the `zpool trim -s zmirror-sysfs` command.
  def test_zpool_sysfs_backing_blockdev_sysfs_s_trim_cancel(self):
    
    trigger_event()

    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]


    assert s.state.what == EntityState.ONLINE


    assert not since_in(Operations.TRIM, s.operations)
    assert RequestType.TRIM not in s.requested

    assert_commands([
      # zmirror should do nothing
    ])


  # the user tells zmirror to request trim again
  def test_zpool_sysfs_backing_blockdev_sysfs_s_trim_request(self):
    
    user_commands.request(RequestType.TRIM, ZDev, pool="zmirror-sysfs", name="zmirror-sysfs-s")


    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    assert s.state.what == EntityState.ONLINE
    assert not since_in(Operations.TRIM, s.operations)

    assert_commands([
      "zpool trim zmirror-sysfs zmirror-sysfs-s"
    ])


  # trimming has started
  def test_zpool_sysfs_backing_blockdev_sysfs_s_trim_start2(self):
    
    trigger_event()

    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]


    assert since_in(Operations.TRIM, s.operations)

    assert_commands([
    ])

  # trimming has finished
  def test_zpool_sysfs_backing_blockdev_sysfs_s_trim_finish(self):
    
    trigger_event()

    s = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    assert not since_in(Operations.TRIM, s.operations)

    assert_commands([
      "zpool offline zmirror-sysfs zmirror-sysfs-s"
    ])

if __name__ == '__main__':
  pytest.main()
