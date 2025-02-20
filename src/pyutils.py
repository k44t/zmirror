from datetime import datetime, timedelta
import os
import errno
import subprocess
import sys
import ctypes
import yaml

from zmirror_logging import log
from ki_utils import TabbedShiftexStream, KdStream


def exec_background(command):
  log.info(f"Starting command in background: `{command}`")
  subprocess.Popen(command, shell=False)
  log.info(f"`{command}` started")


def silent_remove(filename):
  try:
    os.remove(filename)
  except OSError as e:  # this would be "except OSError, e:" before Python 2.6
    if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
      raise  # re-raise exception if a different error occurred


def terminate_thread(thread):
  """Terminates a python thread from another thread.

  :param thread: a threading.Thread instance
  """
  if not thread.isAlive():
    return

  exc = ctypes.py_object(SystemExit)
  res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
    ctypes.c_long(thread.ident), exc)
  if res == 0:
    raise ValueError("nonexistent thread id")
  elif res > 1:
    # """if it returns a number greater than one, you're in trouble,
    # and you should call it again with exc=NULL to revert the effect"""
    ctypes.pythonapi.PyThreadState_SetAsyncExc(thread.ident, None)
    raise SystemError("PyThreadState_SetAsyncExc failed")


def myexec(command):
  log.info(f"Executing command: `{command}`")
  process = subprocess.Popen(command,
                 shell=True,
                 stdout=subprocess.PIPE,
                 stderr=subprocess.PIPE)
  formatted_output = []
  formatted_response = []
  formatted_error = []
  # set blocking to not blocking is necessary so that readline
  # wont block when the process already finished. this only works on linux systems!
  os.set_blocking(process.stdout.fileno(), False)
  os.set_blocking(process.stderr.fileno(), False)
  try:
    timestamp_last_stdout_readline_start = datetime.now()
    timestamp_last_stderr_readline_start = datetime.now()
    timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
    timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
    while process.poll() is None:
      if process.stdout is not None:
        response_line = process.stdout.readline().decode("utf-8").replace("\n", "")
        if response_line != "":
          log.info(f"stdout: {response_line}")
        if response_line != "":
          timestamp_last_stdout_readline_start = datetime.now()
          timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
          timestamp_last_stderr_readline = datetime.now()
      if process.stderr is not None:
        error_line = process.stderr.readline().decode("utf-8").replace("\n", "")
        if error_line != "":
          log.error(f"stderr: {error_line}")
        if error_line != "":
          timestamp_last_stderr_readline_start = datetime.now()
          timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
          timestamp_last_stdout_readline = datetime.now()
      if (process.stderr is not None and error_line == "") \
        and (process.stdout is not None and response_line == ""):
        timestamp_stdout_now = datetime.now()
        timestamp_stderr_now = datetime.now()
        if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)) and \
            timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
          no_output_since = min(timestamp_stderr_now - timestamp_last_stderr_readline_start,
                      timestamp_stdout_now - timestamp_last_stdout_readline_start)
          log.warning(
            f"Command `{command}` had no stderr and stdout output since {no_output_since}.")
          timestamp_last_stdout_readline = timestamp_stdout_now
          timestamp_last_stderr_readline = timestamp_stderr_now
      elif (process.stderr is not None and error_line == ""):
        timestamp_stderr_now = datetime.now()
        if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)):
          log.warning(
            f"Command `{command}` had no stderr output since \
              {timestamp_stderr_now - timestamp_last_stderr_readline_start}.")
          timestamp_last_stderr_readline = timestamp_stderr_now
      elif (process.stdout is not None and response_line == ""):
        timestamp_stdout_now = datetime.now()
        if timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
          log.warning(
            f"Command `{command}` had no stdout output since \
              {timestamp_stdout_now - timestamp_last_stdout_readline_start}.")
          timestamp_last_stdout_readline = timestamp_stdout_now
      if response_line != "":
        formatted_response.append(response_line)
        formatted_output.append(response_line)
      if error_line != "":
        formatted_error.append(error_line)
        formatted_output.append(error_line)
  except Exception:
    pass
  try:
    response = process.stdout.readlines()
    for line in response:
      line = line.decode("utf-8").replace("\n", "")
      if line != "":
        log.info(f"stdout: {line}")
        formatted_response.append(line)
        formatted_output.append(line)
  except Exception:
    pass
  try:
    error = process.stderr.readlines()
    for line in error:
      line = line.decode("utf-8").replace("\n", "")
      if line != "":
        log.error(f"stderr: {line}")
        formatted_error.append(line)
        formatted_output.append(line)
  except Exception:
    pass
  return process.returncode, formatted_output, formatted_response, formatted_error


def load_yaml_cache(cache_file_path):
  try:
    with open(cache_file_path, encoding="utf-8") as stream:
      cache_dict = yaml.full_load(stream)
      if not isinstance(cache_dict, dict):
        cache_dict = dict()
  except BaseException as exception:
    log.error(exception)
    cache_dict = dict()
  return cache_dict


def find_or_create_cache(cache_dict, typ, create_args=None, **kwargs):
  identifier = typ.__name__
  for _, (_, value) in enumerate(kwargs.items()):
    identifier = identifier + "|" + value

  cache = None
  if identifier in cache_dict:
    cache = cache_dict[identifier]

  if not isinstance(cache, typ):
    if create_args is not None:
      kwargs.update(create_args)
    cache = typ(**kwargs)
    cache_dict[identifier] = cache
  return cache


def log_env(env):
  stream = TabbedShiftexStream(sys.stdout)
  for var in env:
    if not var.startswith("_"):
      stream.print_raw(f"{var}:: ")
      stream.indent()
      stream.print(env[var])
      stream.dedent()



def load_yaml_config(config_file_path):
  with open(config_file_path, encoding="utf-8") as config_file:
    config = yaml.full_load(config_file)
    return config


outs = TabbedShiftexStream(sys.stdout)


def print_config(config):
  stream = KdStream(outs)

  outs.newlines(3)
  outs.print("config")
  outs.print("#####################")
  outs.newlines(2)

  stream.print_obj(config)


def remove_yaml_cache(cache_file_path):
  log.info(f"removing {cache_file_path}")
  try:
    os.remove(cache_file_path)
  except Exception as exception:
    log.error(f"failed to remove {cache_file_path}. {str(exception)}")


def save_yaml_cache(cache_dict, cache_file_path):
  log.info("writing cache")
  with open(cache_file_path, 'w', encoding="utf-8") as stream:
    yaml.dump(cache_dict, stream)
  log.info("cache written.")


def copy_attrs(lft, rgt):
  for prop in dir(lft):
    if not prop.startswith("_"):
      setattr(rgt, prop, getattr(lft, prop))
