from zmirror import config
from zmirror.daemon import _resilver_activation_targets
from zmirror.entities import get_zpool_backing_device_state
from zmirror.dataclasses import Operation


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

  assert Operation.RESILVER in opers_a
  assert Operation.RESILVER in opers_b
