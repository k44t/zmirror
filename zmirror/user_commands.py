
import dateparser

from .logging import log
from .dataclasses import *
from .util import myexec, outs, copy_attrs
from . import commands as commands
from kpyutils.kiify import KdStream

import argparse
import sys
import logging
import inspect


class CustomArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        self.output_stream = kwargs.pop('output_stream', sys.stdout)
        super().__init__(*args, **kwargs)

    def print_help(self, file=None):
        if file is None:
            file = self.output_stream
        super().print_help(file)

    def print_usage(self, file=None):
        if file is None:
            file = self.output_stream
        super().print_usage(file)

    def exit(self, status=0, message=None):
        if message:
            self._print_message(message, self.output_stream)
        super().exit(status)


def command_request(request, typ, kwargs):
  constructor_params = inspect.signature(typ).parameters

  # Filter the Namespace to include only the required arguments
  filtered_args = {k: v for k, v in kwargs if k in constructor_params}
  entity = config.find_config(typ, **filtered_args)
  if entity is None:
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: entity not configured")
    return
  if not entity.request(request):
    log.error(f"{make_id_string(make_id(typ, **filtered_args))}: request {request} failed. See previous error messages.")
    return
  log.info(f"{make_id_string(make_id(typ, **filtered_args))}: requested {request} scheduled successfully")

def make_online_command(typ):
  def run(args):
    command_request(Request.ONLINE, typ, args)
  return run

def make_offline_command(typ):
  def run(args):
    command_request(Request.ONLINE, typ, args)
  return run

def make_scrub_command(typ):
  def run(args):
    command_request(Request.ONLINE, typ, args)
    command_request(Request.SCRUB, typ, args)
  return run


def handle_command(args, stream):
  handler = logging.StreamHandler(stream)
  log.addHandler(handler)
  try:

    parser = CustomArgumentParser(prog="zmirror", output_stream=stream)
    subparser = parser.add_subparsers(required=True)


    # scrub_parser = subparser.add_parser('scrub-overdue', parents=[], help='scrub devices that have not been scrubbed for too long')
    # scrub_parser.set_defaults(func=scrub)

    online_parser = subparser.add_parser('online', parents=[], help='online devices')

    online_subs = online_parser.add_subparsers(required=True)

    zpool_parser = CustomArgumentParser(add_help=False, output_stream=stream)
    zpool_parser.add_argument("--name", type=str)

    online_zpool = online_subs.add_parser("zpool", parents=[zpool_parser])
    online_zpool.set_defaults(func=make_online_command(ZPool))


    # scrub_parser.set_defaults(func=request_scrub_all_overdue)
  finally:
    log.removeHandler(handler)