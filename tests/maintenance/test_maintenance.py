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
        entity.state.what = EntityState.ONLINE
      elif type(entity) in {DMCrypt}:
        entity.state.what = EntityState.INACTIVE
      
    for entity in config.config_dict.values():
      if type(entity) == ZDev:
        entity.scrub_interval = "4 weeks"
        entity.trim_interval = "4 weeks"
        entity.update_interval = "4 weeks"

    
    zpool = config.config_dict["ZPool|name:zmirror-sysfs"]
    a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    b = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    c = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-c"]
    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    bak_a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    bak_b = config.config_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-b/sysfs"]

    # the pool is initially online, and so is the main zdev
    cached(zpool).state.what = EntityState.ONLINE
    cached(a).state.what = EntityState.ONLINE

    config.set_log_level("debug")



  




  def setup_method(self, method): #pylint: disable=unused-argument
    pass

  def teardown_method(self, method): #pylint: disable=unused-argument
    commands.commands = []



  def test_resilver_not_overdue(self):

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_update = datetime.now()
    
    rqst = request_overdue(Operation.RESILVER, s)

    assert not rqst


  def test_resilver_overdue(self):

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_update = datetime.now() - timedelta(weeks=6)
    
    rqst = request_overdue(Operation.RESILVER, s)

    assert rqst

    rqst.enact_hierarchy()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key"
    ])

    rqst.cancel(Reason.USER_REQUESTED)





  def test_trim_not_overdue(self):

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_trim = datetime.now()
    
    rqst = request_overdue(Operation.TRIM, s)

    assert not rqst


  def test_trim_overdue(self):

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_trim = datetime.now() - timedelta(weeks=6)
    
    rqst = request_overdue(Operation.TRIM, s)

    assert rqst

    rqst.enact_hierarchy()

    assert_commands([
      "cryptsetup open /dev/disk/by-partlabel/zmirror-sysfs-s zmirror-sysfs-s --key-file ./test/zmirror-key"
    ])


    rqst.cancel(Reason.USER_REQUESTED)

  def test_scrub_not_overdue(self):

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cached(s).last_scrub = datetime.now()
    
    rqst = request_overdue(Operation.SCRUB, s)

    assert not rqst


  def test_scrub_overdue(self):

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
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

    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    cache = cached(s)
    assert cache.state.what == EntityState.ONLINE 
    assert since_in(Operation.RESILVER, cache.operations)


  def test_zdev_sysfs_s_resilver_finish(self):
    trigger_event()
    
    assert_commands([
      # sysfs-s is configured to be taken offline once resilver is done, because it is slower than the other mirror devices
      "zpool scrub -s zmirror-sysfs",
      "zpool scrub zmirror-sysfs"
    ])



  def test_zdev_sysfs_s_scrub_start(self):


    blockdev = config.cache_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]

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



  # this is necessary because we have not allowed all requests to be fulfilled
  # and we don't want the testing process to run until the timers have finished
  def test_shutdown_timers(self):
    for timer in config.timers:
      timer.cancel()
    config.timers = []


