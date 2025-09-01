from .util import myexec as myexec #pylint: disable=redefined-builtin
from .logging import log
from . import config as config
from dataclasses import field, dataclass

@dataclass
class Command:
  command: str

  on_execute: list = field(default_factory=list)

  def execute(self):
    log.info(f"executing command: {self.command}")
    returncode, results, _, errors = myexec(self.command) #pylint: disable=exec-used
    for h in self.on_execute:
      h(self, returncode, results, errors)

  def skip(self):
    log.warning(f"skipping command: {self.command}")
    for h in self.on_execute:
      h(self, 0, [], [])





commands = []

def add_command(command, handler=None, unless_redundant=False):
  if unless_redundant:
    for cmd in commands:
      if cmd.command == command:
        if handler is not None:
          cmd.on_execute.append(handler)
        return cmd
  cmd = Command(command)
  if handler is not None:
    cmd.on_execute.append(handler)
  commands.append(cmd)
  return cmd



def execute_commands():
  global commands
  # seen = set()
  # cmds = [x for x in commands if not (x in seen or seen.add(x))]


  if not config.commands_enabled and len(commands) > 0:
    log.warning("command execution currently disabled.")
  for cmd in commands:
    if config.commands_enabled:
      cmd.execute()
    else:
      cmd.skip()

  commands = []
