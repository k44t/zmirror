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


#pylint: disable=nonlocal-without-binding

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
from zmirror.logging import log

from util.util_stage2 import *

import zmirror.user_commands as user_commands
from zmirror.user_commands import request_overdue


from datetime import datetime, timedelta


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



    
    entities.init_config(config_path="./example-config.yml", cache_path="./tests/commands/res/test_cache.yml")


    for entity in config.cache_dict.values():
      tid = entity_id_string(entity)

      assert entity.state.what == EntityState.DISCONNECTED

      # we are simulating that all disks are connected, which
      # would in a non-simulated state mean that all DMCrypts 
      # are INACTIVE, so we simulate that too.
      if type(entity) in {Disk, Partition}:
        entity.state.what = EntityState.CONNECTED
      elif type(entity) in {DMCrypt}:
        entity.state.what = EntityState.INACTIVE
      
    for entity in config.config_dict.values():
      if type(entity) == ZDev:
        entity.scrub_interval = "4 weeks"
        entity.trim_interval = "4 weeks"
        entity.update_interval = "4 weeks"

    
    zpool = config.config_dict["zpool|name:zmirror-sysfs"]
    a = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    b = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    c = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-c"]
    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    bak_a = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    bak_b = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-b/sysfs"]

    # the pool is initially online, and so is the main zdev
    cached(zpool).state.what = EntityState.CONNECTED
    cached(a).state.what = EntityState.CONNECTED

    config.set_log_level("debug")

  @classmethod
  def teardown_class(cls):
    zmirror.commands.stop_workers()








  def setup_method(self, method): #pylint: disable=unused-argument
    pass

  def teardown_method(self, method): #pylint: disable=unused-argument
    commands.commands = []



  def test_resilver_not_overdue(self):

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_update = datetime.now()
    
    rqst = request_overdue(Operation.RESILVER, s)

    assert not rqst


  def test_resilver_overdue(self):

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_update = datetime.now() - timedelta(weeks=6)
    
    rqst = request_overdue(Operation.RESILVER, s)

    assert rqst

    rqst.enact_hierarchy()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key"
    ])

    rqst.cancel(Reason.USER_REQUESTED)





  def test_trim_not_overdue(self):

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_trim = datetime.now()
    
    rqst = request_overdue(Operation.TRIM, s)

    assert not rqst


  def test_trim_overdue(self):

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_trim = datetime.now() - timedelta(weeks=6)
    
    rqst = request_overdue(Operation.TRIM, s)

    assert rqst

    rqst.enact_hierarchy()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key"
    ])


    rqst.cancel(Reason.USER_REQUESTED)

  def test_scrub_not_overdue(self):

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_scrub = datetime.now()
    
    rqst = request_overdue(Operation.SCRUB, s)

    assert not rqst


  def test_scrub_overdue(self):

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_scrub = datetime.now() - timedelta(weeks=6)
    
    rqst = request_overdue(Operation.SCRUB, s)

    assert rqst

    rqst.enact_hierarchy()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key"
    ])

  # dmcrypt of sysfs-s appears
  def test_dmcrypt_sysfs_s_online(self):

    
    trigger_event()
    
    assert_commands([
      "zpool online zmirror-sysfs zmirror-sysfs-s"
    ])


  def test_zdev_sysfs_s_online(self):
        
    trigger_event()
    
    assert_commands([])

    s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cache = cached(s)
    assert cache.state.what == EntityState.ACTIVE
    assert since_in(Operation.RESILVER, cache.operations)


  def test_zdev_sysfs_s_resilver_finish(self):
    trigger_event()
    
    assert_commands([
      # sysfs-s is configured to be taken offline once resilver is done, because it is slower than the other mirror devices
      "zpool scrub -s zmirror-sysfs",
      "zpool scrub zmirror-sysfs"
    ])



  def test_zdev_sysfs_s_scrub_start(self):


    blockdev = config.cache_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

    s = uncached(blockdev)

    assert RequestType.SCRUB in s.requested

    rqst =  s.requested[RequestType.SCRUB]

    assert rqst.timer is False
    
    assert blockdev.operations == []

    trigger_event()

    assert since_in(Operation.SCRUB, blockdev.operations)


    assert_commands([
      
    ])

    assert RequestType.SCRUB not in s.requested


  def test_disk_activates_on_child_online(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["partition|name:zmirror-sysfs-s"]
    disk_cache = cached(disk)

    disk_cache.state.what = EntityState.CONNECTED
    disk.handle_child_online(partition, EntityState.DISCONNECTED)

    assert disk_cache.state.what == EntityState.ACTIVE


  def test_disk_deactivates_to_connected_on_children_offline(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["partition|name:zmirror-sysfs-s"]
    disk_cache = cached(disk)
    partition_cache = cached(partition)

    disk_cache.state.what = EntityState.ACTIVE
    partition_cache.state.what = EntityState.DISCONNECTED
    disk.handle_child_offline(partition, EntityState.CONNECTED)

    assert disk_cache.state.what == EntityState.CONNECTED


  def test_disk_onlined_with_online_child_becomes_active(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["partition|name:zmirror-sysfs-s"]
    disk_cache = cached(disk)
    partition_cache = cached(partition)

    disk_cache.state.what = EntityState.DISCONNECTED
    partition_cache.state.what = EntityState.CONNECTED
    handle_onlined(disk_cache)

    assert disk_cache.state.what == EntityState.ACTIVE


  def test_partition_activates_on_child_online(self):
    partition = config.config_dict["partition|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["dm-crypt|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)

    partition_cache.state.what = EntityState.CONNECTED
    partition.handle_child_online(dmcrypt, EntityState.INACTIVE)

    assert partition_cache.state.what == EntityState.ACTIVE


  def test_partition_deactivates_to_connected_on_children_offline(self):
    partition = config.config_dict["partition|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["dm-crypt|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)
    dmcrypt_cache = cached(dmcrypt)

    partition_cache.state.what = EntityState.ACTIVE
    dmcrypt_cache.state.what = EntityState.DISCONNECTED
    partition.handle_child_offline(dmcrypt, EntityState.CONNECTED)

    assert partition_cache.state.what == EntityState.CONNECTED


  def test_partition_onlined_with_online_child_becomes_active(self):
    partition = config.config_dict["partition|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["dm-crypt|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)
    dmcrypt_cache = cached(dmcrypt)

    partition_cache.state.what = EntityState.DISCONNECTED
    dmcrypt_cache.state.what = EntityState.CONNECTED
    handle_onlined(partition_cache)

    assert partition_cache.state.what == EntityState.ACTIVE


  def test_zfs_volume_activates_on_child_online(self):
    volume = config.config_dict["zfs-volume|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)

    volume_cache.state.what = EntityState.CONNECTED
    volume.handle_child_online(zdev, EntityState.INACTIVE)

    assert volume_cache.state.what == EntityState.ACTIVE


  def test_zfs_volume_deactivates_to_connected_on_children_offline(self):
    volume = config.config_dict["zfs-volume|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    zdev_cache = cached(zdev)

    volume_cache.state.what = EntityState.ACTIVE
    zdev_cache.state.what = EntityState.DISCONNECTED
    volume.handle_child_offline(zdev, EntityState.CONNECTED)

    assert volume_cache.state.what == EntityState.CONNECTED


  def test_zfs_volume_onlined_with_online_child_becomes_active(self):
    volume = config.config_dict["zfs-volume|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    zdev_cache = cached(zdev)

    volume_cache.state.what = EntityState.DISCONNECTED
    zdev_cache.state.what = EntityState.CONNECTED
    handle_onlined(volume_cache)

    assert volume_cache.state.what == EntityState.ACTIVE


  def test_dmcrypt_activates_on_child_online(self):
    dmcrypt = config.config_dict["dm-crypt|name:zmirror-sysfs-s"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    dmcrypt_cache = cached(dmcrypt)

    dmcrypt_cache.state.what = EntityState.CONNECTED
    dmcrypt.handle_child_online(zdev, EntityState.INACTIVE)

    assert dmcrypt_cache.state.what == EntityState.ACTIVE


  def test_dmcrypt_deactivates_to_connected_on_children_offline(self):
    dmcrypt = config.config_dict["dm-crypt|name:zmirror-sysfs-s"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    dmcrypt_cache = cached(dmcrypt)
    zdev_cache = cached(zdev)

    dmcrypt_cache.state.what = EntityState.ACTIVE
    zdev_cache.state.what = EntityState.DISCONNECTED
    dmcrypt.handle_child_offline(zdev, EntityState.CONNECTED)

    assert dmcrypt_cache.state.what == EntityState.CONNECTED



  # this is necessary because we have not allowed all requests to be fulfilled
  # and we don't want the testing process to run until the timers have finished
  def test_shutdown_timers(self):
    for timer in config.timers:
      timer.cancel()
    config.timers = []
