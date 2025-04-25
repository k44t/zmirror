

import json
import inspect
from zmirror.daemon import handle
from .util_stage1 import open_local, get_frame_data
import zmirror.entities as entities



def trigger_event():
  _, _, fn_name = get_frame_data(1)

  with open_local("res/" + fn_name + ".json", "r", levels=1) as f:
    src = f.read()
  event = json.loads(src)
  handle(event)


def do_nothing(*args): #pylint: disable=unused-argument
  pass


def prepare_config_and_cache():
  package_path, _, _ = get_frame_data(1)
  entities.init_config(cache_path=f"{package_path}/res/cache.yml", config_path=f"{package_path}/res/config.yml")