#!/bin/python3

import pytest

from util.util_stage1 import *
from util.util_stage2 import *

from zmirror.dataclasses import *
import zmirror.commands
import zmirror.entities as entities


@pytest.fixture(scope="class", autouse=True)
def setup_before_all_methods():
  insert_zpool_status_stub()
  insert_dev_exists_stub()
  insert_get_zfs_volume_mode_stub()
  insert_find_provisioning_mode_stub()


class Tests():

  @classmethod
  def setup_class(cls):
    entities.init_config(config_path="./example-config.yml", cache_path="./tests/commands/res/test_cache.yml")
    config.timeout = 15

    for entity in config.cache_dict.values():
      if type(entity) in {Disk, Part}:
        entity.state.what = EntityState.CONNECTED
      elif type(entity) in {Crypt}:
        entity.state.what = EntityState.INACTIVE
      else:
        entity.state.what = EntityState.DISCONNECTED

    zpool = config.config_dict["zpool|name:zmirror-sysfs"]
    a = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
    cached(zpool).state.what = EntityState.CONNECTED
    cached(a).state.what = EntityState.CONNECTED

  @classmethod
  def teardown_class(cls):
    zmirror.commands.stop_workers()

  def teardown_method(self, method):  # pylint: disable=unused-argument
    commands.commands = []

  def test_disk_activates_on_child_online(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    disk_cache = cached(disk)

    disk_cache.state.what = EntityState.CONNECTED
    disk.handle_child_online(partition, EntityState.DISCONNECTED)

    assert disk_cache.state.what == EntityState.ACTIVE

  def test_disk_deactivates_to_connected_on_children_offline(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    disk_cache = cached(disk)
    partition_cache = cached(partition)

    disk_cache.state.what = EntityState.ACTIVE
    partition_cache.state.what = EntityState.DISCONNECTED
    disk.handle_child_offline(partition, EntityState.CONNECTED)

    assert disk_cache.state.what == EntityState.CONNECTED

  def test_disk_onlined_with_online_child_becomes_active(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    disk_cache = cached(disk)
    partition_cache = cached(partition)

    disk_cache.state.what = EntityState.DISCONNECTED
    partition_cache.state.what = EntityState.CONNECTED
    handle_onlined(disk_cache)

    assert disk_cache.state.what == EntityState.ACTIVE

  def test_partition_activates_on_child_online(self):
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)

    partition_cache.state.what = EntityState.CONNECTED
    partition.handle_child_online(dmcrypt, EntityState.INACTIVE)

    assert partition_cache.state.what == EntityState.ACTIVE

  def test_partition_deactivates_to_connected_on_children_offline(self):
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)
    dmcrypt_cache = cached(dmcrypt)

    partition_cache.state.what = EntityState.ACTIVE
    dmcrypt_cache.state.what = EntityState.DISCONNECTED
    partition.handle_child_offline(dmcrypt, EntityState.CONNECTED)

    assert partition_cache.state.what == EntityState.CONNECTED

  def test_partition_onlined_with_online_child_becomes_active(self):
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)
    dmcrypt_cache = cached(dmcrypt)

    partition_cache.state.what = EntityState.DISCONNECTED
    dmcrypt_cache.state.what = EntityState.CONNECTED
    handle_onlined(partition_cache)

    assert partition_cache.state.what == EntityState.ACTIVE

  def test_partition_load_initial_state_becomes_active_with_online_child(self):
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    dmcrypt_cache = cached(dmcrypt)
    old_dev_exists = config.dev_exists

    dmcrypt_cache.state.what = EntityState.ACTIVE
    config.dev_exists = lambda path: path == partition.dev_path()
    try:
      assert partition.load_initial_state() == EntityState.ACTIVE
    finally:
      config.dev_exists = old_dev_exists

  def test_disk_load_initial_state_becomes_active_with_online_child(self):
    disk = config.config_dict["disk|uuid:00000000-0000-0000-0000-000000000004"]
    partition = config.config_dict["part|name:zmirror-sysfs-s"]
    partition_cache = cached(partition)
    old_dev_exists = config.dev_exists

    partition_cache.state.what = EntityState.ACTIVE
    config.dev_exists = lambda path: path == disk.dev_path()
    try:
      assert disk.load_initial_state() == EntityState.ACTIVE
    finally:
      config.dev_exists = old_dev_exists

  def test_dmcrypt_load_initial_state_becomes_active_with_online_child(self):
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    zdev_cache = cached(zdev)
    old_dev_exists = config.dev_exists

    zdev_cache.state.what = EntityState.ACTIVE
    config.dev_exists = lambda path: path == dmcrypt.dev_path()
    try:
      assert dmcrypt.load_initial_state() == EntityState.ACTIVE
    finally:
      config.dev_exists = old_dev_exists

  def test_zfs_volume_activates_on_child_online(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)

    volume_cache.state.what = EntityState.READY
    volume.handle_child_online(zdev, EntityState.INACTIVE)

    assert volume_cache.state.what == EntityState.ACTIVE

  def test_zfs_volume_deactivates_to_ready_on_children_offline(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    zdev_cache = cached(zdev)

    volume_cache.state.what = EntityState.ACTIVE
    zdev_cache.state.what = EntityState.DISCONNECTED
    volume.handle_child_offline(zdev, EntityState.CONNECTED)

    assert volume_cache.state.what == EntityState.READY

  def test_zfs_volume_onlined_with_online_child_becomes_active(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    zdev_cache = cached(zdev)

    volume_cache.state.what = EntityState.DISCONNECTED
    zdev_cache.state.what = EntityState.CONNECTED
    handle_onlined(volume_cache)

    assert volume_cache.state.what == EntityState.ACTIVE

  def test_zfs_volume_onlined_without_online_child_becomes_ready(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    zdev_cache = cached(zdev)

    volume_cache.state.what = EntityState.DISCONNECTED
    zdev_cache.state.what = EntityState.INACTIVE
    handle_onlined(volume_cache)

    assert volume_cache.state.what == EntityState.READY

  def test_zfs_volume_update_initial_state_becomes_active_with_online_child(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    pool = config.config_dict["zpool|name:zmirror-bak-a"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    pool_cache = cached(pool)
    zdev_cache = cached(zdev)

    pool_cache.state.what = EntityState.CONNECTED
    zdev_cache.state.what = EntityState.ACTIVE

    assert volume.update_initial_state() == EntityState.ACTIVE

  def test_zfs_volume_update_initial_state_becomes_ready_without_online_child(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    pool = config.config_dict["zpool|name:zmirror-bak-a"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    pool_cache = cached(pool)
    zdev_cache = cached(zdev)

    pool_cache.state.what = EntityState.CONNECTED
    zdev_cache.state.what = EntityState.INACTIVE

    assert volume.update_initial_state() == EntityState.READY

  def test_zfs_volume_offline_request_fails_without_command(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    zdev_cache = cached(zdev)

    volume_cache.state.what = EntityState.ACTIVE
    zdev_cache.state.what = EntityState.INACTIVE
    request = volume.request(RequestType.OFFLINE)
    request.enact_hierarchy()

    assert request.handled is True
    assert request.succeeded is False
    assert RequestType.OFFLINE not in volume.requested
    assert commands.commands == []

  def test_zfs_volume_offline_request_succeeds_after_child_deactivation(self):
    volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    sibling_volume = config.config_dict["zvol|pool:zmirror-bak-a|name:big"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    volume_cache = cached(volume)
    sibling_cache = cached(sibling_volume)
    zdev_cache = cached(zdev)

    volume.requested.clear()
    zdev.requested.clear()
    commands.commands = []

    volume_cache.state.what = EntityState.ACTIVE
    sibling_cache.state.what = EntityState.READY
    zdev_cache.state.what = EntityState.ACTIVE

    request = volume.request(RequestType.OFFLINE)
    request.enact_hierarchy()

    assert request.handled is False
    assert RequestType.OFFLINE in volume.requested
    assert_commands([
      "zpool offline zmirror-sysfs zvol/zmirror-bak-a/sysfs"
    ])

    commands.commands = []
    zdev.handle_deactivated()

    assert volume_cache.state.what == EntityState.READY
    assert request.handled is True
    assert request.succeeded is True
    assert RequestType.OFFLINE not in volume.requested

  def test_zpool_offline_request_waits_for_all_zvol_children(self):
    pool = config.config_dict["zpool|name:zmirror-bak-a"]
    sysfs_volume = config.config_dict["zvol|pool:zmirror-bak-a|name:sysfs"]
    big_volume = config.config_dict["zvol|pool:zmirror-bak-a|name:big"]
    sysfs_zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zvol/zmirror-bak-a/sysfs"]
    big_zdev = config.config_dict["zdev|pool:zmirror-big|name:zvol/zmirror-bak-a/big"]

    pool_cache = cached(pool)
    sysfs_cache = cached(sysfs_volume)
    big_cache = cached(big_volume)
    sysfs_zdev_cache = cached(sysfs_zdev)
    big_zdev_cache = cached(big_zdev)

    pool.requested.clear()
    sysfs_volume.requested.clear()
    big_volume.requested.clear()
    sysfs_zdev.requested.clear()
    big_zdev.requested.clear()
    commands.commands = []

    pool_cache.state.what = EntityState.CONNECTED
    sysfs_cache.state.what = EntityState.ACTIVE
    big_cache.state.what = EntityState.ACTIVE
    sysfs_zdev_cache.state.what = EntityState.ACTIVE
    big_zdev_cache.state.what = EntityState.ACTIVE

    request = pool.request(RequestType.OFFLINE)
    request.enact_hierarchy()

    assert request.handled is False
    assert RequestType.OFFLINE in pool.requested
    assert_commands([
      "zpool offline zmirror-sysfs zvol/zmirror-bak-a/sysfs",
      "zpool offline zmirror-big zvol/zmirror-bak-a/big"
    ])

    commands.commands = []
    sysfs_zdev.handle_deactivated()

    assert sysfs_cache.state.what == EntityState.READY
    assert request.handled is False
    assert request.succeeded is False
    assert RequestType.OFFLINE in pool.requested
    assert commands.commands == []

    big_zdev.handle_deactivated()

    assert big_cache.state.what == EntityState.READY
    assert request.handled is False
    assert request.succeeded is False
    assert RequestType.OFFLINE in pool.requested
    assert_commands([
      "zpool export zmirror-bak-a"
    ])

  def test_dmcrypt_activates_on_child_online(self):
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    dmcrypt_cache = cached(dmcrypt)

    dmcrypt_cache.state.what = EntityState.CONNECTED
    dmcrypt.handle_child_online(zdev, EntityState.INACTIVE)

    assert dmcrypt_cache.state.what == EntityState.ACTIVE

  def test_dmcrypt_deactivates_to_connected_on_children_offline(self):
    dmcrypt = config.config_dict["crypt|name:zmirror-sysfs-s"]
    zdev = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
    dmcrypt_cache = cached(dmcrypt)
    zdev_cache = cached(zdev)

    dmcrypt_cache.state.what = EntityState.ACTIVE
    zdev_cache.state.what = EntityState.DISCONNECTED
    dmcrypt.handle_child_offline(zdev, EntityState.CONNECTED)

    assert dmcrypt_cache.state.what == EntityState.CONNECTED
