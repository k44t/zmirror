from zmirror.daemon import handle, update_vdev_error_state
from zmirror.entities import find_or_create_cache, refresh_all_vdev_error_state_from_status
from zmirror.dataclasses import ZDev, EntityState
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


def test_vdev_clear_event_clears_errors_even_for_offline_target():
  old_cache_dict = config.cache_dict
  try:
    config.cache_dict = {}
    cache = find_or_create_cache(ZDev, pool="tank", name="disk1")
    cache.state.what = EntityState.INACTIVE
    cache.errors = True

    handled = handle({
      "ZEVENT_SUBCLASS": "vdev_clear",
      "ZEVENT_POOL": "tank",
      "ZEVENT_VDEV_PATH": "/dev/disk1",
      "ZEVENT_VDEV_STATE_STR": "OFFLINE",
    })

    assert handled is True
    assert cache.errors is False
  finally:
    config.cache_dict = old_cache_dict


def test_status_update_clears_errors_when_counters_are_zero_even_if_vdev_offline():
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
        "disk1": {"state": "OFFLINE", "errors": False}
      }
    })

    assert cache.errors is False
  finally:
    config.cache_dict = old_cache_dict
    config.zfs_blockdevs = old_blockdevs


def test_refresh_all_vdev_error_state_from_status_updates_from_zpool_status(monkeypatch):
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

    assert cache.errors is False
  finally:
    config.cache_dict = old_cache_dict
    config.zfs_blockdevs = old_blockdevs
