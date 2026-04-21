#!/bin/python3

import os
import pytest

from datetime import datetime, timedelta

from util.util_stage1 import find_in_file, legacy_zpool_status_to_json
from util.util_stage2 import assert_commands

import zmirror.commands as commands
import zmirror.entities as entities
from zmirror import config
from zmirror.dataclasses import *
from zmirror.user_commands import request_overdue


@pytest.fixture(autouse=True)
def setup_test_config():
  commands_res = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "commands", "res"))
  maintenance_res = os.path.join(os.path.dirname(__file__), "res")

  def get_zpool_status_stub(zpool):
    path = os.path.join(commands_res, f"setup_class.{zpool}.zpool-status.txt")
    with open(path, "r", encoding="utf8") as file:
      return legacy_zpool_status_to_json(zpool, file.read())

  def dev_exists_stub(dev):
    return find_in_file(os.path.join(maintenance_res, "devlinks.txt"), dev)

  def get_zfs_volume_mode_stub(zfs_path):
    zfs_path = zfs_path.replace("/", "_")
    path = os.path.join(commands_res, f"setup_class.{zfs_path}.zfs_volume_mode.txt")
    with open(path, "r", encoding="utf8") as file:
      content = file.read()
      return content or None

  config.get_zpool_status = get_zpool_status_stub
  config.dev_exists = dev_exists_stub
  config.get_zfs_volume_mode = get_zfs_volume_mode_stub
  config.find_provisioning_mode = lambda _zfs_path: os.path.join(commands_res, "provisioning_mode.txt")

  entities.init_config(config_path="./example-config.yml", cache_path="./tests/commands/res/test_cache.yml")
  config.timeout = 15

  for entity in config.cache_dict.values():
    if type(entity) in {Disk, Part}:
      entity.state.what = EntityState.CONNECTED
    elif type(entity) in {Crypt}:
      entity.state.what = EntityState.INACTIVE

  for entity in config.config_dict.values():
    if type(entity) == ZDev:
      entity.scrub_interval = "4 weeks"
      entity.trim_interval = "4 weeks"
      entity.update_interval = "4 weeks"
      entity.available_update_interval = None

  zpool = config.config_dict["zpool|name:zmirror-sysfs"]
  a = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-a"]
  cached(zpool).state.what = EntityState.CONNECTED
  cached(a).state.what = EntityState.CONNECTED

  commands.commands = []
  yield
  commands.commands = []
  commands.stop_workers()


def test_request_overdue_scrub_is_noop_while_marker_active():
  s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
  cache = cached(s)
  cache.last_scrub = datetime.now() - timedelta(weeks=6)
  cache.state.what = EntityState.ACTIVE
  cache.operations = [Since(Operation.SCRUB)]

  rqst = s.request(RequestType.SCRUB)

  rqst.enact_hierarchy()

  assert since_in(Operation.SCRUB, cache.operations)
  assert RequestType.SCRUB not in s.requested
  assert_commands([])


def test_overdue_scrub_request_short_circuits_while_marker_active():
  s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
  cache = cached(s)
  cache.last_scrub = datetime.now() - timedelta(weeks=6)
  cache.state.what = EntityState.ACTIVE
  cache.operations = [Since(Operation.SCRUB)]

  rqst = request_overdue(Operation.SCRUB, s)

  assert rqst

  rqst.enact_hierarchy()

  assert since_in(Operation.SCRUB, cache.operations)
  assert RequestType.SCRUB not in s.requested
  assert_commands([])


def test_successful_scrub_can_trigger_offline_handler():
  s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
  cache = cached(s)
  cache.state.what = EntityState.ACTIVE
  cache.operations = [Since(Operation.SCRUB)]
  s.on_scrub_succeeded = ["offline"]
  s.on_trimmed = []

  handle_scrub_finished(cache, successful_scrub=True)

  assert not since_in(Operation.SCRUB, cache.operations)
  assert_commands([
    "zpool offline zmirror-sysfs zmirror-sysfs-s"
  ])


def test_load_initial_state_uses_disappeared_flow_for_stale_operations(monkeypatch):
  s = config.config_dict["zdev|pool:zmirror-sysfs|name:zmirror-sysfs-s"]
  cache = cached(s)
  cache.state.what = EntityState.ACTIVE
  cache.operations = [
    Since(Operation.SCRUB),
    Since(Operation.TRIM),
    Since(Operation.RESILVER),
  ]

  monkeypatch.setattr(config, "get_zpool_backing_device_state", lambda _pool, _dev: (EntityState.ACTIVE, set()))

  state = s.load_initial_state()

  assert state == EntityState.ACTIVE
  assert not since_in(Operation.SCRUB, cache.operations)
  assert not since_in(Operation.TRIM, cache.operations)
  assert not since_in(Operation.RESILVER, cache.operations)
  assert_commands([])
