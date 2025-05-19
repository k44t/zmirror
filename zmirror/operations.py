
import dateparser

from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs
from .entities import *
from . import commands as commands
from .daemon import daemon
from kpyutils.kiify import KdStream

import argparse
import sys
import logging
import inspect

def request_scrub_all_overdue(*args):
  log.info("starting zfs scrubs if necessary")
  def possibly_scrub(dev):
    if isinstance(dev, ZFSBackingBlockDevice):
      cache = find_or_create_cache(ZFSBackingBlockDevice, pool=dev.pool, dev=dev.dev_name())
      if dev.scrub_interval is not None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(dev.scrub_interval)
        if (cache.last_scrubbed is None or allowed_delta > cache.last_scrubbed):
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev_name()}' must be scrubbed")
          entity = load_config_for_cache(cache)
          entity.request(Request.ONLINE)
          entity.request(Request.SCRUB)
        else:
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' does not have to be scrubbed")
  iterate_content_tree(config.config_root, possibly_scrub)
  iterate_content_tree(config.config_root, do_enact_request)


def do_enact_request(entity):
  if isinstance(entity, Entity):
    entity.enact_request()


def request(rqst, typ, all_dependencies=False, **identifiers):
  tid = make_id_string(make_id(typ, **identifiers))
  entity = load_config_for_id(tid)
  if config is None:
    raise ValueError(f"{tid} not configured")
  result = entity.request(rqst, all_dependencies = all_dependencies)
  if result:
    iterate_content_tree(config.config_root, do_enact_request)
    return True
  return False

