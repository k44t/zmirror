from datetime import datetime
import queue

import pytest

from kpyutils.scheduler import Scheduler, _next_after_any, parse_schedule, parse_weekday_ranges
from zmirror import config
from zmirror.dataclasses import ZMirror
import zmirror.entities as entities
from zmirror.user_commands import LIST_DEFAULT_KEYS, LIST_KEYS, validate_list_columns


def test_parse_weekday_ranges_supports_wraparound():
  weekdays = parse_weekday_ranges(["fri-mon"])

  assert len(weekdays) == 2
  assert weekdays[0].start == 4
  assert weekdays[0].end == 6
  assert weekdays[1].start == 0
  assert weekdays[1].end == 0


def test_next_after_respects_calendar_filters():
  schedule = parse_schedule(
    times=["03:00:00"],
    days=["10-15"],
    months=["3"],
    weekdays=["fri-mon"],
  )

  next_run = _next_after_any([schedule], datetime(2026, 3, 11, 4, 0, 0))

  assert next_run == datetime(2026, 3, 13, 3, 0, 0)


def test_scheduler_cancel_stops_instance():
  scheduler = Scheduler(
    schedules=[parse_schedule(times=[":00"]), parse_schedule(times=["00:00"])],
    callback=lambda: None,
  )

  scheduler.start()

  scheduler.cancel()

  assert scheduler._running is False
  assert scheduler._thread is None


def test_parse_schedule_requires_times_list():
  with pytest.raises(ValueError, match="times must be a list"):
    parse_schedule(times="03:00:00")


def test_available_update_fields_not_in_default_list_output():
  assert "available_update_overdue" not in LIST_DEFAULT_KEYS
  assert "available_update_interval" not in LIST_DEFAULT_KEYS
  assert "state" in LIST_KEYS
  assert "status" not in LIST_KEYS
  assert "available_update_overdue" in LIST_KEYS
  assert "available_update_interval" in LIST_KEYS


def test_validate_list_columns_rejects_unknown_names():
  with pytest.raises(ValueError, match="unknown keys: status"):
    validate_list_columns(["status"], "keys")


def test_regular_status_scheduler_defaults_to_every_ten_minutes():
  root = ZMirror()

  assert root.regular_status_scheduler == [{"times": ["00:00", "10:00", "20:00", "30:00", "40:00", "50:00"]}]


def test_configure_internal_scheduler_starts_regular_status_scheduler(monkeypatch):
  created = []

  class FakeScheduler:
    def __init__(self, schedules, callback, dispatch):
      self.schedules = schedules
      self.callback = callback
      self.dispatch = dispatch
      self.started = False
      created.append(self)

    def start(self):
      self.started = True

    def cancel(self):
      self.started = False

  old_is_daemon = config.is_daemon
  old_event_queue = config.event_queue
  old_config_root = config.config_root
  old_update_scheduler = config.update_scheduler
  old_maintenance_scheduler = config.maintenance_scheduler
  old_regular_status_scheduler = config.regular_status_scheduler
  try:
    config.is_daemon = True
    config.event_queue = queue.Queue()
    config.config_root = ZMirror(update_scheduler=[], maintenance_scheduler=[])
    config.update_scheduler = None
    config.maintenance_scheduler = None
    config.regular_status_scheduler = None
    monkeypatch.setattr(entities, "Scheduler", FakeScheduler)

    entities._configure_internal_scheduler()

    assert len(created) == 1
    assert created[0].started is True
    assert config.regular_status_scheduler is created[0]
  finally:
    entities._stop_internal_schedulers()
    config.is_daemon = old_is_daemon
    config.event_queue = old_event_queue
    config.config_root = old_config_root
    config.update_scheduler = old_update_scheduler
    config.maintenance_scheduler = old_maintenance_scheduler
    config.regular_status_scheduler = old_regular_status_scheduler
