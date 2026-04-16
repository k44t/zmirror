import io
import logging

from zmirror.zmirror import make_arg_parser
from zmirror.user_commands import handle_set_command, handle_get_command
from zmirror.daemon import handle
from zmirror import config


def test_enable_disable_log_full_events_parser_wiring():
  parser = make_arg_parser()

  enable_args = parser.parse_args(["enable", "log-full-events"])
  disable_args = parser.parse_args(["disable", "log-full-events"])
  get_args = parser.parse_args(["get", "log-full-events"])

  assert hasattr(enable_args, "func")
  assert hasattr(disable_args, "func")
  assert hasattr(get_args, "func")


def test_set_get_log_full_events_property():
  prev_log_events = config.log_events
  prev_log_full_events = config.log_full_events
  try:
    handle_set_command({"property": "log-full-events", "value": "yes"})
    assert config.log_events is False
    assert config.log_full_events is True

    out = io.StringIO()
    handle_get_command({"property": "log-full-events"}, out)
    assert out.getvalue() == "yes"

    handle_set_command({"property": "log-events", "value": "yes"})
    assert config.log_events is True
    assert config.log_full_events is False

    handle_set_command({"property": "log-full-events", "value": "no"})
    assert config.log_events is False
    assert config.log_full_events is False

    handle_set_command({"property": "log-events", "value": "no"})
    assert config.log_events is False
    assert config.log_full_events is False
  finally:
    config.log_events = prev_log_events
    config.log_full_events = prev_log_full_events


def test_log_full_events_logs_unrestricted_env(caplog):
  prev_log_events = config.log_events
  prev_log_full_events = config.log_full_events
  try:
    event = {"ACTION": "add", "CUSTOM_KEY": "x"}

    config.log_events = True
    config.log_full_events = False
    with caplog.at_level(logging.INFO, logger="zmirror"):
      handle(event)
    restricted_text = "\n".join(caplog.messages)
    assert "ACTION" in restricted_text
    assert "CUSTOM_KEY" not in restricted_text

    caplog.clear()

    config.log_events = False
    config.log_full_events = True
    with caplog.at_level(logging.INFO, logger="zmirror"):
      handle(event)
    full_text = "\n".join(caplog.messages)
    assert "ACTION" in full_text
    assert "CUSTOM_KEY" in full_text
  finally:
    config.log_events = prev_log_events
    config.log_full_events = prev_log_full_events
