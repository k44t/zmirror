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


  if config.config_root.disable_commands:
    log.warning("command execution currently disabled via config file")
  for cmd in commands:
    if config.config_root.disable_commands:
      log.info(f"skipping command: {cmd}")
    else:
      log.info(f"executing command: {cmd}")
      returncode, _, _, _ = exec(cmd) #pylint: disable=exec-used
      if returncode != 0:
        log.info(f"command failed: {cmd}")

  commands = []
