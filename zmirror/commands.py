from .util import myexec as exec#pylint: disable=redefined-builtin
from .logging import log
from . import config as config



commands = []

def add_command(command):
  commands.append(command)


def execute_commands():
  global commands
  # seen = set()                                                    
  # cmds = [x for x in commands if not (x in seen or seen.add(x))]

  for cmd in commands:
    if not config.disable_commands:
      _execute_command(cmd)
  commands = []


def _execute_command(command):
  returncode, _, _, _ = exec(command) #pylint: disable=exec-used
  if returncode != 0:
    log.warning(f"command failed: {command}")
