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

    
    zpool = config.config_dict["ZPool|name:zmirror-sysfs"]
    a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    b = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-b"]
    c = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-c"]
    s = config.config_dict["ZDev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    bak_a = config.config_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    bak_b = config.config_dict["ZDev|pool:zmirror-sysfs|name:zvol/zmirror-bak-b/sysfs"]

    # the pool is initially online
    cached(zpool).state = Since(EntityState.ONLINE, datetime.now())





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



  # physical device of sysfs-a gets plugged-in (by user)
  # disk of sysfs-a appears (udev: add)
  def test_disk_sysfs_a_online(self):
    pass

