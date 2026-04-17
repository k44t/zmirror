from datetime import datetime

import pytest

from kpyutils.scheduler import Scheduler, _next_after_any, parse_schedule, parse_weekday_ranges
from zmirror.user_commands import LIST_DEFAULT_KEYS, LIST_KEYS


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
  assert "available_update_overdue" in LIST_KEYS
  assert "available_update_interval" in LIST_KEYS
