
import dateparser

from .logging import log
from .dataclasses import ZFSBackingBlockDevice, ZFSBackingBlockDeviceCache, ZFSOperationState, ZFSBackingBlockDeviceOutput
from .util import myexec, outs, copy_attrs
from .entities import *
from . import commands as commands
from .daemon import daemon
from kpyutils.kiify import KdStream




def scrub_all_overdue():
  log.info("starting zfs scrubs if necessary")
  def possibly_scrub(dev):
    if isinstance(dev, ZFSBackingBlockDevice):
      cache = find_or_create_cache(ZFSBackingBlockDeviceCache, pool=dev.pool, dev=dev.dev_name())
      if dev.scrub_interval is not None:
        # parsing the schedule delta will result in a timestamp calculated from now
        allowed_delta = dateparser.parse(dev.scrub_interval)
        if (cache.last_scrubbed is None or allowed_delta > cache.last_scrubbed):
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev_name()}' must be scrubbed")
          if cache.operation is not None and cache.operation.what == ZFSOperationState.NONE:
            commands.add_command(f"zpool scrub {dev.pool}")
        else:
          log.info(f"zfs pool '{dev.pool}' dev '{dev.dev}' does not have to be scrubbed")
  iterate_content_tree(config.config_root, possibly_scrub)