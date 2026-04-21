from zmirror import config
from zmirror.daemon import DelayedResilverStartCheckEvent, _clear_pending_resilver_start_check, _handle_delayed_resilver_start, _reconcile_status_operations, _reliable_resilver_targets, _resilver_activation_targets
from zmirror.entities import find_or_create_cache
from zmirror.entities import get_zpool_backing_device_state
from zmirror.dataclasses import EntityState, Operation, Since, ZDev, handle_resilver_started, since_in


def _snapshot(pool, scan_function, scan_state, devices):
  leaf_vdevs = {}
  for name, attrs in devices.items():
    leaf_vdevs[name] = {
      "name": name,
      "state": attrs.get("state", "ONLINE"),
      "read_errors": "0",
      "write_errors": "0",
      "checksum_errors": "0",
    }
    if attrs.get("operations") is not None:
      leaf_vdevs[name]["operations"] = attrs["operations"]
    if attrs.get("scan_processed") is not None:
      leaf_vdevs[name]["scan_processed"] = attrs["scan_processed"]

  return {
    "pools": {
      pool: {
        "scan_stats": {
          "function": scan_function,
          "state": scan_state,
        },
        "vdevs": {
          pool: {
            "vdevs": {
              "mirror-0": {
                "name": "mirror-0",
                "vdevs": leaf_vdevs,
              }
            }
          }
        },
      }
    }
  }


def _collect(pool_status, pool="tank"):
  from zmirror.daemon import _collect_pool_status_snapshot

  return _collect_pool_status_snapshot(pool, pool_status)


def test_resilver_targets_use_scan_processed_when_present():
  snap = _collect(_snapshot("tank", "RESILVER", "SCANNING", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE", "scan_processed": "1.2G"},
  }))

  assert _resilver_activation_targets(snap) == {"b"}


def test_reliable_resilver_targets_use_only_per_vdev_information():
  snap = _collect(_snapshot("tank", "RESILVER", "SCANNING", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE", "scan_processed": "1.2G"},
  }))

  assert _reliable_resilver_targets(snap) == {"b"}


def test_resilver_targets_fallback_to_all_online_when_scan_processed_missing():
  snap = _collect(_snapshot("tank", "RESILVER", "SCANNING", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE"},
    "c": {"state": "OFFLINE"},
  }))

  assert _resilver_activation_targets(snap) == {"a", "b"}


def test_resilver_targets_empty_when_not_resilver_scanning():
  snap = _collect(_snapshot("tank", "RESILVER", "FINISHED", {
    "a": {"state": "ONLINE", "scan_processed": "1.2G"},
  }))

  assert _resilver_activation_targets(snap) == set()


def test_get_zpool_backing_device_state_uses_scan_processed_for_resilver_activation(monkeypatch):
  status = _snapshot("tank", "RESILVER", "SCANNING", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE", "scan_processed": "2.0G"},
  })
  monkeypatch.setattr(config, "get_zpool_status", lambda _pool: status)

  _state_a, opers_a = get_zpool_backing_device_state("tank", "a")
  _state_b, opers_b = get_zpool_backing_device_state("tank", "b")

  assert Operation.RESILVER not in opers_a
  assert Operation.RESILVER in opers_b


def test_get_zpool_backing_device_state_fallbacks_to_all_online_without_scan_processed(monkeypatch):
  status = _snapshot("tank", "RESILVER", "SCANNING", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE"},
  })
  monkeypatch.setattr(config, "get_zpool_status", lambda _pool: status)

  _state_a, opers_a = get_zpool_backing_device_state("tank", "a")
  _state_b, opers_b = get_zpool_backing_device_state("tank", "b")

  assert Operation.RESILVER not in opers_a
  assert Operation.RESILVER not in opers_b


def test_get_zpool_backing_device_state_uses_per_vdev_trim_operation(monkeypatch):
  status = _snapshot("tank", "NONE", "FINISHED", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE", "operations": ["trim"]},
  })
  monkeypatch.setattr(config, "get_zpool_status", lambda _pool: status)

  _state_a, opers_a = get_zpool_backing_device_state("tank", "a")
  _state_b, opers_b = get_zpool_backing_device_state("tank", "b")

  assert Operation.TRIM not in opers_a
  assert Operation.TRIM in opers_b


def test_get_zpool_backing_device_state_marks_scrub_active_for_online_devices(monkeypatch):
  status = _snapshot("tank", "SCRUB", "SCANNING", {
    "a": {"state": "ONLINE"},
    "b": {"state": "ONLINE"},
    "c": {"state": "OFFLINE"},
  })
  monkeypatch.setattr(config, "get_zpool_status", lambda _pool: status)

  _state_a, opers_a = get_zpool_backing_device_state("tank", "a")
  _state_b, opers_b = get_zpool_backing_device_state("tank", "b")
  _state_c, opers_c = get_zpool_backing_device_state("tank", "c")

  assert Operation.SCRUB in opers_a
  assert Operation.SCRUB in opers_b
  assert Operation.SCRUB not in opers_c


def test_get_zpool_backing_device_state_does_not_mark_canceled_scrub_active(monkeypatch):
  status = _snapshot("tank", "SCRUB", "CANCELED", {
    "a": {"state": "ONLINE"},
  })
  monkeypatch.setattr(config, "get_zpool_status", lambda _pool: status)

  _state_a, opers_a = get_zpool_backing_device_state("tank", "a")

  assert Operation.SCRUB not in opers_a


def test_delayed_resilver_start_marks_all_online_devices_when_scan_still_active(monkeypatch):
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}
    cache_a = find_or_create_cache(ZDev, pool="tank", name="a")
    cache_b = find_or_create_cache(ZDev, pool="tank", name="b")
    cache_a.state.what = cache_b.state.what = EntityState.ACTIVE
    monkeypatch.setattr(config, "get_zpool_status", lambda _pool: _snapshot("tank", "RESILVER", "SCANNING", {
      "a": {"state": "ONLINE"},
      "b": {"state": "ONLINE"},
    }))

    assert _handle_delayed_resilver_start(DelayedResilverStartCheckEvent("tank")) is True
    assert since_in(Operation.RESILVER, cache_a.operations)
    assert since_in(Operation.RESILVER, cache_b.operations)
  finally:
    _clear_pending_resilver_start_check("tank")
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_delayed_resilver_start_is_noop_when_scan_finished(monkeypatch):
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  try:
    config.cache_dict = {}
    config.config_dict = {}
    cache_a = find_or_create_cache(ZDev, pool="tank", name="a")
    monkeypatch.setattr(config, "get_zpool_status", lambda _pool: _snapshot("tank", "RESILVER", "FINISHED", {
      "a": {"state": "ONLINE"},
    }))

    assert _handle_delayed_resilver_start(DelayedResilverStartCheckEvent("tank")) is False
    assert not since_in(Operation.RESILVER, cache_a.operations)
  finally:
    _clear_pending_resilver_start_check("tank")
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict


def test_delayed_resilver_start_does_not_fallback_when_pool_already_has_updating_device(monkeypatch):
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  old_blockdevs = config.zfs_blockdevs
  try:
    config.cache_dict = {}
    config.config_dict = {}
    config.zfs_blockdevs = {"tank": {"a": object(), "b": object()}}
    cache_a = find_or_create_cache(ZDev, pool="tank", name="a")
    cache_b = find_or_create_cache(ZDev, pool="tank", name="b")
    cache_a.state.what = cache_b.state.what = EntityState.ACTIVE
    handle_resilver_started(cache_a)
    monkeypatch.setattr(config, "get_zpool_status", lambda _pool: _snapshot("tank", "RESILVER", "SCANNING", {
      "a": {"state": "ONLINE"},
      "b": {"state": "ONLINE"},
    }))

    assert _handle_delayed_resilver_start(DelayedResilverStartCheckEvent("tank")) is False
    assert since_in(Operation.RESILVER, cache_a.operations)
    assert not since_in(Operation.RESILVER, cache_b.operations)
  finally:
    _clear_pending_resilver_start_check("tank")
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.zfs_blockdevs = old_blockdevs


def test_reconcile_status_operations_removes_disappeared_operations():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  old_zfs_blockdevs = config.zfs_blockdevs
  try:
    config.cache_dict = {}
    config.config_dict = {}
    config.zfs_blockdevs = {"tank": {"a": object()}}
    zdev_a = ZDev(pool="tank", name="a")
    config.config_dict[entity_id_string(zdev_a)] = zdev_a
    cache_a = find_or_create_cache(ZDev, pool="tank", name="a")
    cache_a.state.what = EntityState.ACTIVE
    cache_a.operations = [
      Since(Operation.SCRUB),
      Since(Operation.TRIM),
      Since(Operation.RESILVER),
    ]

    snap = _collect(_snapshot("tank", "NONE", "FINISHED", {
      "a": {"state": "ONLINE"},
    }))

    assert _reconcile_status_operations(snap) is True
    assert not since_in(Operation.SCRUB, cache_a.operations)
    assert not since_in(Operation.TRIM, cache_a.operations)
    assert not since_in(Operation.RESILVER, cache_a.operations)
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.zfs_blockdevs = old_zfs_blockdevs


def test_reconcile_status_operations_adds_scrub_and_trim_only_for_status_online_devices():
  old_cache_dict = config.cache_dict
  old_zfs_blockdevs = config.zfs_blockdevs
  try:
    config.cache_dict = {}
    config.zfs_blockdevs = {"tank": {"a": object(), "b": object()}}
    cache_a = find_or_create_cache(ZDev, pool="tank", name="a")
    cache_b = find_or_create_cache(ZDev, pool="tank", name="b")
    cache_a.state.what = cache_b.state.what = EntityState.ACTIVE

    snap = _collect(_snapshot("tank", "SCRUB", "SCANNING", {
      "a": {"state": "ONLINE", "operations": ["trim"]},
      "b": {"state": "OFFLINE", "operations": ["trim"]},
    }))

    assert _reconcile_status_operations(snap) is True
    assert since_in(Operation.SCRUB, cache_a.operations)
    assert since_in(Operation.TRIM, cache_a.operations)
    assert not since_in(Operation.SCRUB, cache_b.operations)
    assert not since_in(Operation.TRIM, cache_b.operations)
  finally:
    config.cache_dict = old_cache_dict
    config.zfs_blockdevs = old_zfs_blockdevs


def test_reconcile_status_operations_removes_canceled_scrub():
  old_cache_dict = config.cache_dict
  old_config_dict = config.config_dict
  old_zfs_blockdevs = config.zfs_blockdevs
  try:
    config.cache_dict = {}
    config.config_dict = {}
    config.zfs_blockdevs = {"tank": {"a": object()}}
    zdev_a = ZDev(pool="tank", name="a")
    config.config_dict[entity_id_string(zdev_a)] = zdev_a
    cache_a = find_or_create_cache(ZDev, pool="tank", name="a")
    cache_a.state.what = EntityState.ACTIVE
    cache_a.operations = [Since(Operation.SCRUB)]

    snap = _collect(_snapshot("tank", "SCRUB", "CANCELED", {
      "a": {"state": "ONLINE"},
    }))

    assert _reconcile_status_operations(snap) is True
    assert not since_in(Operation.SCRUB, cache_a.operations)
  finally:
    config.cache_dict = old_cache_dict
    config.config_dict = old_config_dict
    config.zfs_blockdevs = old_zfs_blockdevs
