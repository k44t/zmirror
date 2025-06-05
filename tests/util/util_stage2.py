

import json
import inspect
from zmirror.daemon import handle
from zmirror.user_commands import enact_requests
from .util_stage1 import open_local, get_frame_data
import zmirror.entities as entities
import zmirror.commands as commands
import re

from itertools import zip_longest

def assert_commands(cmds):
  for a, b in zip_longest(cmds, commands.commands):
    if b is None:
      raise ValueError(f"expected command missing: {a}")
    command = b.command
    if a is None:
      raise ValueError(f"unexpected command: {command}")
    if isinstance(a, re.Pattern):
      assert a.match(command)
    else:
      assert a == command


def trigger_event():
  _, _, fn_name = get_frame_data(1)

  with open_local("res/" + fn_name + ".json", "r", levels=1) as f:
    src = f.read()
  event = json.loads(src)
  handle(event)
  enact_requests()


def do_nothing(*args): #pylint: disable=unused-argument
  pass


def prepare_config_and_cache():
  package_path, _, _ = get_frame_data(1)
  entities.init_config(cache_path=f"{package_path}/res/cache.yml", config_path=f"{package_path}/res/config.yml")