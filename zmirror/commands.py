from dataclasses import dataclass
import queue
import threading
from promise import Promise

from . import config as config
from .logging import log
from .util import myexec as myexec #pylint: disable=redefined-builtin


@dataclass
class CommandResultEvent:
  cmd: object
  returncode: int
  results: list
  errors: list


@dataclass
class Command:
  command: str
  input: str

  def __init__(self, command, input=None):
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

_event_queue = None
_work_queue = queue.Queue()
_workers = []
_stop_worker = object()
_max_workers = 5


def _worker_loop(event_queue):
  while True:
    cmd = _work_queue.get()
    if cmd is _stop_worker:
      break
    try:
      log.info(f"executing command: {cmd.command}")
      returncode, results, _, errors = myexec(cmd.command, input=cmd.input)
    except BaseException as ex: # pylint: disable=broad-exception-caught
      returncode = 1
      results = []
      errors = [f"worker execution failed: {ex}"]
    event_queue.put(CommandResultEvent(cmd, returncode, results, errors))


def start_workers(event_queue, num_workers=1):
  global _event_queue
  _event_queue = event_queue
  target = min(max(0, num_workers), _max_workers)
  while len(_workers) < target:
    worker = threading.Thread(target=_worker_loop, args=(event_queue,), daemon=True)
    worker.start()
    _workers.append(worker)


def stop_workers():
  global _event_queue

  while not _work_queue.empty():
    try:
      _work_queue.get_nowait()
    except queue.Empty:
      break

  for _worker in _workers:
    _work_queue.put(_stop_worker)

  for worker in _workers:
    worker.join(timeout=1)

  _workers.clear()
  _event_queue = None


def add_script(script, unless_redundant=False, input=None):
  if unless_redundant:
    for cmd in commands:
      if cmd.command == script:
        return cmd
  cmd = Command(script, input=input)
  commands.append(cmd)
  return cmd


def execute_commands():
  global commands
  while commands:
    if not config.commands_enabled and len(commands) > 0:
      log.warning("command execution currently disabled.")
    run_commands = commands
    commands = []
    if _event_queue is not None:
      start_workers(_event_queue, num_workers=min(len(run_commands), _max_workers))
    for cmd in run_commands:
      if config.commands_enabled:
        if _event_queue is None:
          cmd.execute()
        else:
          _work_queue.put(cmd)
      else:
        cmd.skip()
