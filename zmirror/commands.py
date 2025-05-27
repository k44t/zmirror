from .util import myexec as exec#pylint: disable=redefined-builtin
from .logging import log
from . import config as config



commands = []

def add_command(command, unless_redundant = False):
  if unless_redundant:
    if command not in commands:
      commands.append(command)
  else:
    commands.append(command)


def execute_commands():
  global commands
  # seen = set()
  # cmds = [x for x in commands if not (x in seen or seen.add(x))]


  if not config.commands_enabled and len(commands) > 0:
    log.warning("command execution currently disabled.")
  for cmd in commands:
    if not config.commands_enabled:
      log.warning(f"skipping command: {cmd}")
    else:
      log.info(f"executing command: {cmd}")
      returncode, _, _, errors = exec(cmd) #pylint: disable=exec-used
      if returncode != 0:
        log.warning(f"command failed: {cmd}\n\t" + "\n\t".join(errors))


  commands = []
