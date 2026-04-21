import logging

from zmirror.daemon import handle, update_vdev_error_state
from zmirror import commands
from zmirror.entities import finalize_init, find_or_create_cache, refresh_all_vdev_error_state_from_status
from zmirror.dataclasses import Crypt, ZDev, ZPool, ZMirror, EntityState, Operation, RequestType, Request, Since, entity_id_string, since_in
from zmirror import config


def _snapshot_with_one_vdev(pool, name, state, read="0", write="0", cksum="0", scan_errors="0"):
  return {
    "pools": {
      pool: {
        "scan_stats": {"errors": scan_errors},
        "vdevs": {
          pool: {
            "vdevs": {
              name: {
                "name": name,
                "state": state,
                "read_errors": read,
                "write_errors": write,
                "checksum_errors": cksum,
              }
            }
          }
        },
      }
    }
  }


def test_vdev_clear_event_does_not_change_errors_for_offline_target(monkeypatch):
  old_cache_dict = config.cache_dict
  try:
    config.cache_dict = {}
    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.INACTIVE
    cache.errors = True
    monkeypatch.setattr(
      config,
      "get_zpool_status",
      lambda pool: _snapshot_with_one_vdev(pool, "disk1", state="OFFLINE", read="0", write="0", cksum="0"),
    )

    handled = handle({
      "ZEVENT_SUBCLASS": "vdev_clear",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/disk1",
      "ZEVENT_VDEV_STATE_STR": "OFFLINE",
    })

    assert handled is True
    assert cache.errors is True
  finally:
    config.cache_dict = old_cache_dict


def test_status_update_sets_errors_when_online_cache_sees_non_online_vdev_state():
  old_cache_dict = config.cache_dict
  old_blockdevs = config.zfs_blockdevs
  try:
    config.cache_dict = {}
    config.zfs_blockdevs = {"tank": {"disk1": object()}}

    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.ACTIVE
    cache.errors = True

    update_vdev_error_state({
      "zpool": "tank",
      "devices": {
        "disk1": {"state": "OFFLINE", "errors": True}
      }
    })

    assert cache.errors is True
  finally:
    config.cache_dict = old_cache_dict
    config.zfs_blockdevs = old_blockdevs


def test_vdev_online_unavail_keeps_zdev_deactivated_sets_error_and_fails_online_request():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}

    zdev = ZDev(pool="tank", name="disk1")
    config.config_dict[entity_id_string(zdev)] = zdev
    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.INACTIVE
    cache.errors = False

    request = Request(RequestType.ONLINE, zdev, 0)
    zdev.requested[RequestType.ONLINE] = request

    handled = handle({
      "ZEVENT_SUBCLASS": "vdev_online",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/disk1",
      "ZEVENT_VDEV_STATE_STR": "UNAVAIL",
    })

    assert handled is True
    assert cache.state.what == EntityState.INACTIVE
    assert cache.errors is True
    assert request.handled is True
    assert request.succeeded is False
    assert RequestType.ONLINE not in zdev.requested
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_parent_offline_failed_zdev_offline_command_still_disconnects_child():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  old_commands_enabled = config.commands_enabled
  old_commands = commands.commands
  try:
    config.cache_dict = {}
    config.config_dict = {}
    commands.commands = []
    config.commands_enabled = False

    crypt = Crypt(name="crypt1")
    zdev = ZDev(pool="tank", name="crypt1")
    zdev.parent = crypt

    config.config_dict[entity_id_string(crypt)] = crypt
    config.config_dict[entity_id_string(zdev)] = zdev

    crypt_cache = find_or_create_cache(Crypt, name="crypt1")
    crypt_cache.state.what = EntityState.DISCONNECTED
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="crypt1")
    zdev_cache.state.what = EntityState.ACTIVE

    request = zdev.request(RequestType.OFFLINE)
    request.enact_hierarchy()
    commands.execute_commands()

    assert zdev_cache.state.what == EntityState.DISCONNECTED
    assert request.handled is True
    assert request.succeeded is True
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.commands_enabled = old_commands_enabled
    commands.commands = old_commands


def test_parent_online_failed_zdev_offline_command_does_not_disconnect_child():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  old_commands_enabled = config.commands_enabled
  old_commands = commands.commands
  try:
    config.cache_dict = {}
    config.config_dict = {}
    commands.commands = []
    config.commands_enabled = False

    crypt = Crypt(name="crypt1")
    zdev = ZDev(pool="tank", name="crypt1")
    zdev.parent = crypt

    config.config_dict[entity_id_string(crypt)] = crypt
    config.config_dict[entity_id_string(zdev)] = zdev

    crypt_cache = find_or_create_cache(Crypt, name="crypt1")
    crypt_cache.state.what = EntityState.CONNECTED
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="crypt1")
    zdev_cache.state.what = EntityState.ACTIVE

    request = zdev.request(RequestType.OFFLINE)
    request.enact_hierarchy()
    commands.execute_commands()

    assert zdev_cache.state.what == EntityState.ACTIVE
    assert request.handled is True
    assert request.succeeded is False
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.commands_enabled = old_commands_enabled
    commands.commands = old_commands


def test_statechange_unavail_sets_error_without_state_change():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}
    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.ACTIVE
    cache.errors = False

    handled = handle({
      "ZEVENT_SUBCLASS": "statechange",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/disk1",
      "ZEVENT_VDEV_STATE_STR": "UNAVAIL",
    })

    assert handled is True
    assert cache.state.what == EntityState.ACTIVE
    assert cache.errors is True
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_statechange_faulted_with_offline_parent_clears_error_without_state_change():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}

    crypt = Crypt(name="crypt1")
    crypt.unpluggable = True
    zdev = ZDev(pool="tank", name="crypt1")
    zdev.parent = crypt

    config.config_dict[entity_id_string(crypt)] = crypt
    config.config_dict[entity_id_string(zdev)] = zdev

    crypt_cache = find_or_create_cache(Crypt, name="crypt1")
    crypt_cache.state.what = EntityState.DISCONNECTED
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="crypt1")
    zdev_cache.state.what = EntityState.ACTIVE
    zdev_cache.errors = True

    handled = handle({
      "ZEVENT_SUBCLASS": "statechange",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/mapper/crypt1",
      "ZEVENT_VDEV_STATE_STR": "FAULTED",
    })

    assert handled is True
    assert zdev_cache.state.what == EntityState.ACTIVE
    assert zdev_cache.errors is False
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_statechange_faulted_without_offline_parent_sets_error():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}

    zdev = ZDev(pool="tank", name="disk1")
    config.config_dict[entity_id_string(zdev)] = zdev
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    zdev_cache.state.what = EntityState.ACTIVE
    zdev_cache.errors = False

    handled = handle({
      "ZEVENT_SUBCLASS": "statechange",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/disk1",
      "ZEVENT_VDEV_STATE_STR": "FAULTED",
    })

    assert handled is True
    assert zdev_cache.state.what == EntityState.ACTIVE
    assert zdev_cache.errors is True
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_removed_event_with_offline_parent_clears_error_without_state_change():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}

    crypt = Crypt(name="crypt1")
    crypt.unpluggable = True
    zdev = ZDev(pool="tank", name="crypt1")
    zdev.parent = crypt

    config.config_dict[entity_id_string(crypt)] = crypt
    config.config_dict[entity_id_string(zdev)] = zdev

    crypt_cache = find_or_create_cache(Crypt, name="crypt1")
    crypt_cache.state.what = EntityState.DISCONNECTED
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="crypt1")
    zdev_cache.state.what = EntityState.ACTIVE
    zdev_cache.errors = True

    handled = handle({
      "ZEVENT_SUBCLASS": "removed",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/mapper/crypt1",
      "ZEVENT_VDEV_STATE_STR": "REMOVED",
    })

    assert handled is True
    assert zdev_cache.state.what == EntityState.ACTIVE
    assert zdev_cache.errors is False
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_removed_event_without_offline_parent_sets_error_without_state_change():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}

    zdev = ZDev(pool="tank", name="disk1")
    config.config_dict[entity_id_string(zdev)] = zdev
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    zdev_cache.state.what = EntityState.ACTIVE
    zdev_cache.errors = False

    handled = handle({
      "ZEVENT_SUBCLASS": "removed",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/disk1",
      "ZEVENT_VDEV_STATE_STR": "REMOVED",
    })

    assert handled is True
    assert zdev_cache.state.what == EntityState.ACTIVE
    assert zdev_cache.errors is True
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_statechange_faulted_with_offline_parent_and_not_unpluggable_sets_error():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}

    crypt = Crypt(name="crypt1")
    crypt.unpluggable = False
    zdev = ZDev(pool="tank", name="crypt1")
    zdev.parent = crypt

    config.config_dict[entity_id_string(crypt)] = crypt
    config.config_dict[entity_id_string(zdev)] = zdev

    crypt_cache = find_or_create_cache(Crypt, name="crypt1")
    crypt_cache.state.what = EntityState.DISCONNECTED
    zdev_cache = find_or_create_cache(ZDev, pool="tank", name="crypt1")
    zdev_cache.state.what = EntityState.ACTIVE
    zdev_cache.errors = False

    handled = handle({
      "ZEVENT_SUBCLASS": "statechange",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/mapper/crypt1",
      "ZEVENT_VDEV_STATE_STR": "FAULTED",
    })

    assert handled is True
    assert zdev_cache.state.what == EntityState.ACTIVE
    assert zdev_cache.errors is True
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_refresh_all_vdev_error_state_from_status_uses_vdev_state_as_error(monkeypatch):
  old_cache_dict = config.cache_dict
  old_blockdevs = config.zfs_blockdevs
  try:
    config.cache_dict = {}
    config.zfs_blockdevs = {"tank": {"disk1": object()}}

    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.ACTIVE
    cache.errors = True

    monkeypatch.setattr(
      config,
      "get_zpool_status",
      lambda pool: _snapshot_with_one_vdev(pool, "disk1", state="OFFLINE", read="0", write="0", cksum="0"),
    )

    refresh_all_vdev_error_state_from_status()

    assert cache.errors is True
  finally:
    config.cache_dict = old_cache_dict
    config.zfs_blockdevs = old_blockdevs


def test_refresh_all_vdev_error_state_from_status_reconciles_operations(monkeypatch, caplog):
  old_cache_dict = config.cache_dict
  old_blockdevs = config.zfs_blockdevs
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}
    config.zfs_blockdevs = {"tank": {"disk1": object()}}

    zdev = ZDev(pool="tank", name="disk1")
    config.config_dict[entity_id_string(zdev)] = zdev
    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.ACTIVE
    cache.operations = [Since(Operation.SCRUB), Since(Operation.TRIM)]

    monkeypatch.setattr(
      config,
      "get_zpool_status",
      lambda pool: _snapshot_with_one_vdev(pool, "disk1", state="ONLINE", read="0", write="0", cksum="0"),
    )

    with caplog.at_level(logging.INFO, logger="zmirror"):
      refresh_all_vdev_error_state_from_status()

    assert not since_in(Operation.SCRUB, cache.operations)
    assert not since_in(Operation.TRIM, cache.operations)
    text = "\n".join(caplog.messages)
    assert "scrub disappeared from status" in text
    assert "trim disappeared from status" in text
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.zfs_blockdevs = old_blockdevs


def test_finalize_init_logs_active_operations(caplog):
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  old_config_root = config.config_root
  try:
    config.cache_dict = {}
    config.config_dict = {}
    config.config_root = ZMirror(update_interval="4 weeks", trim_interval="4 weeks", scrub_interval="4 weeks")

    zdev = ZDev(pool="tank", name="disk1")
    config.config_dict[entity_id_string(zdev)] = zdev
    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.ACTIVE
    cache.operations = [Since(Operation.SCRUB), Since(Operation.TRIM)]

    with caplog.at_level(logging.INFO, logger="zmirror"):
      finalize_init(zdev, None, None)

    text = "\n".join(caplog.messages)
    assert "ACTIVE (active operations: scrub, trim)" in text
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.config_root = old_config_root


def test_status_update_does_not_set_pool_errors_for_admin_offline_degraded_pool():
  old_cache_dict = config.cache_dict
  try:
    config.cache_dict = {}

    cache = find_or_create_cache(ZPool, name="tank")
    cache.state.what = EntityState.ACTIVE
    cache.errors = False

    update_vdev_error_state({
      "zpool": "tank",
      "scrub_errors": 0,
      "pool": {
        "state": "DEGRADED",
        "status": "One or more devices has been taken offline by the administrator.",
        "error_count": "0",
      },
      "devices": {
        "disk1": {"state": "ONLINE", "errors": False},
        "disk2": {"state": "OFFLINE", "errors": True},
      },
    })

    assert cache.errors is False
  finally:
    config.cache_dict = old_cache_dict


def test_status_update_sets_pool_errors_for_non_admin_degraded_pool_state():
  old_cache_dict = config.cache_dict
  try:
    config.cache_dict = {}

    cache = find_or_create_cache(ZPool, name="tank")
    cache.state.what = EntityState.ACTIVE
    cache.errors = False

    update_vdev_error_state({
      "zpool": "tank",
      "scrub_errors": 0,
      "pool": {"state": "DEGRADED", "status": "One or more devices could not be used because the label is missing or invalid."},
      "devices": {},
    })

    assert cache.errors is True
  finally:
    config.cache_dict = old_cache_dict


def test_status_update_does_not_set_pool_errors_for_offline_pool_state():
  old_cache_dict = config.cache_dict
  try:
    config.cache_dict = {}

    cache = find_or_create_cache(ZPool, name="tank")
    cache.state.what = EntityState.ACTIVE
    cache.errors = True

    update_vdev_error_state({
      "zpool": "tank",
      "scrub_errors": 0,
      "pool": {"state": "OFFLINE"},
      "devices": {},
    })

    assert cache.errors is False
  finally:
    config.cache_dict = old_cache_dict


def test_status_update_leaves_offline_zmirror_pool_errors_unchanged():
  old_cache_dict = config.cache_dict
  try:
    config.cache_dict = {}

    cache = find_or_create_cache(ZPool, name="tank")
    cache.state.what = EntityState.DISCONNECTED
    cache.errors = False

    update_vdev_error_state({
      "zpool": "tank",
      "scrub_errors": 1,
      "pool": {"state": "DEGRADED"},
      "devices": {},
    })

    assert cache.errors is False
  finally:
    config.cache_dict = old_cache_dict
