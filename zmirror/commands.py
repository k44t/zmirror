from .util import myexec as myexec #pylint: disable=redefined-builtin
from .logging import log
from . import config as config
from dataclasses import field, dataclass
from promise import Promise

@dataclass
class Command:
  command: str
  input: str
  
  def __init__(self, command, input = None):
    self.command = command
    self.input = input
  
    def make_promise(resolve, reject):
      self.resolve = resolve
      self.reject = reject

    self.promise = Promise(make_promise)
    self.promise.command = self
  
  def then(self, did_fulfill, did_reject):
    return self.promise.then(did_fulfill, did_reject)
  def done(self, did_fulfill, did_reject):
    return self.promise.done(did_fulfill, did_reject)
  def catch(self, on_rejection):
    return self.promise.catch(on_rejection)

  def handle(self, returncode: int, results: list, errors: list):
    if returncode == 0:
      self.resolve((self, returncode, results, errors))
    else:
      self.reject(ValueError((self, returncode, results, errors)))


  def execute(self):
    log.info(f"executing command: {self.command}")
    returncode, results, _, errors = myexec(self.command, input=self.input)
    self.handle(returncode, results, errors)

  def skip(self):
    log.warning(f"skipping command: {self.command}")
    self.reject(ValueError("command was skipped"))





commands = []

def add_command(command, unless_redundant=False, input=None):
  if unless_redundant:
    for cmd in commands:
      if cmd.command == command:
        return cmd
  cmd = Command(command, input=input)
  commands.append(cmd)
  return cmd



def execute_commands():
  global commands
  # seen = set()
  # cmds = [x for x in commands if not (x in seen or seen.add(x))]
  while commands:
    if not config.commands_enabled and len(commands) > 0:
      log.warning("command execution currently disabled.")
    run_commands = commands
    commands = []
    for cmd in run_commands:
      if config.commands_enabled:
        cmd.execute()
      else:
        cmd.skip()

