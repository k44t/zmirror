from datetime import datetime, timedelta
import os
import errno
import subprocess
import sys
import ctypes
import sqlite3
import yaml

from .logging import log
from kpyutils.kiify import TabbedShiftexStream, KdStream






def read_file(path, encoding="utf-8"):
  try:
    with open(path, 'r', encoding=encoding) as file:
      return file.read()
  except:
      return None



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


def myexec(command, input = None):
  log.debug(f"Executing command: `{command}`")
  process = subprocess.Popen(command,
                 shell=True,
                 stdout=subprocess.PIPE,
                 stderr=subprocess.PIPE, 
                 stdin=subprocess.PIPE)
  formatted_output = []
  formatted_response = []
  formatted_error = []
  # set blocking to not blocking is necessary so that readline
  # wont block when the process already finished. this only works on linux systems!
  os.set_blocking(process.stdout.fileno(), False)
  os.set_blocking(process.stderr.fileno(), False)

  if input:
    if isinstance(input, str):
      input = input.encode("utf-8")
    process.communicate(input=input)
  try:
    timestamp_last_stdout_readline_start = datetime.now()
    timestamp_last_stderr_readline_start = datetime.now()
    timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
    timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
    while process.poll() is None:
      if process.stdout is not None:
        response_line = process.stdout.readline().decode("utf-8").replace("\n", "")
        if response_line != "":
          log.debug(f"stdout: {response_line}")
        if response_line != "":
          timestamp_last_stdout_readline_start = datetime.now()
          timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
          timestamp_last_stderr_readline = datetime.now()
      if process.stderr is not None:
        error_line = process.stderr.readline().decode("utf-8").replace("\n", "")
        if error_line != "":
          log.debug(f"stderr: {error_line}")
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
          log.debug(
            f"Command `{command}` had no stderr and stdout output since {no_output_since}.")
          timestamp_last_stdout_readline = timestamp_stdout_now
          timestamp_last_stderr_readline = timestamp_stderr_now
      elif (process.stderr is not None and error_line == ""):
        timestamp_stderr_now = datetime.now()
        if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)):
          log.debug(
            f"Command `{command}` had no stderr output since \
              {timestamp_stderr_now - timestamp_last_stderr_readline_start}.")
          timestamp_last_stderr_readline = timestamp_stderr_now
      elif (process.stdout is not None and response_line == ""):
        timestamp_stdout_now = datetime.now()
        if timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
          log.debug(
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
        log.debug(f"stdout: {line}")
        formatted_response.append(line)
        formatted_output.append(line)
  except Exception:
    pass
  try:
    error = process.stderr.readlines()
    for line in error:
      line = line.decode("utf-8").replace("\n", "")
      if line != "":
        log.debug(f"stderr: {line}")
        formatted_error.append(line)
        formatted_output.append(line)
  except Exception:
    pass
  if process.returncode != 0:
      log.debug(f"Command `{command}` failed with return code {process.returncode}.")
  return process.returncode, formatted_output, formatted_response, formatted_error


def init_cache_db(cache_file_path):
  conn = sqlite3.connect(cache_file_path)
  conn.execute("PRAGMA foreign_keys = ON")

  def has_column(table_name, column_name):
    rows = conn.execute(f"PRAGMA table_info({table_name})")
    return any(row[1] == column_name for row in rows)

  def rename_or_copy_column(old_name, new_name, colspec, copy_expr=None):
    if has_column("cache_entries", new_name):
      return
    if has_column("cache_entries", old_name):
      try:
        conn.execute(f"ALTER TABLE cache_entries RENAME COLUMN {old_name} TO {new_name}")
      except Exception:
        conn.execute(f"ALTER TABLE cache_entries ADD COLUMN {new_name} {colspec}")
        expr = old_name if copy_expr is None else copy_expr
        conn.execute(f"UPDATE cache_entries SET {new_name} = {expr} WHERE {new_name} IS NULL")
      return
    conn.execute(f"ALTER TABLE cache_entries ADD COLUMN {new_name} {colspec}")

  version = conn.execute("PRAGMA user_version").fetchone()[0]
  if version == 0:
    conn.execute("""
      CREATE TABLE IF NOT EXISTS cache_entries (
        id TEXT PRIMARY KEY,
        state_what TEXT,
        state_since TEXT,
        added INTEGER,
        last_online TEXT,
        last_update TEXT,
        last_trim TEXT,
        last_scrub TEXT,
        errors INTEGER DEFAULT 0
      )
    """)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS cache_operations (
        id INTEGER PRIMARY KEY,
        entity_id TEXT NOT NULL,
        what TEXT NOT NULL,
        since TEXT,
        UNIQUE(entity_id, what),
        FOREIGN KEY (entity_id) REFERENCES cache_entries(id) ON DELETE CASCADE
      )
    """)
    conn.execute("PRAGMA user_version = 4")
    conn.commit()

  if version == 1:
    rename_or_copy_column("added_at", "added", "INTEGER")
    conn.execute("UPDATE cache_entries SET added = CAST(strftime('%s','now') AS INTEGER) WHERE added IS NULL")
    rename_or_copy_column("has_errors", "errors", "INTEGER DEFAULT 0")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()

  if version == 2:
    rename_or_copy_column("added_at", "added", "INTEGER")
    conn.execute("UPDATE cache_entries SET added = CAST(strftime('%s','now') AS INTEGER) WHERE added IS NULL")
    rename_or_copy_column("has_errors", "errors", "INTEGER DEFAULT 0")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()

  if version == 3:
    rename_or_copy_column("added_at", "added", "INTEGER")
    conn.execute("UPDATE cache_entries SET added = CAST(strftime('%s','now') AS INTEGER) WHERE added IS NULL")
    rename_or_copy_column("has_errors", "errors", "INTEGER DEFAULT 0")
    conn.execute("PRAGMA user_version = 4")
    conn.commit()

  return conn


def remove_cache_db(cache_file_path):
  log.info(f"removing {cache_file_path}")
  try:
    os.remove(cache_file_path)
  except Exception as exception:
    log.error(f"failed to remove {cache_file_path}. {str(exception)}")



def find_or_create_cache(cache_dict, typ, create_args=None, identifier_prefix=None, **kwargs):
  from .dataclasses import make_id_string  # pylint: disable=import-outside-toplevel

  id_values = {}
  if identifier_prefix is not None:
    for _, (key, value) in enumerate(identifier_prefix.items()):
      id_values[key] = value

  for _, (key, value) in enumerate(kwargs.items()):
    id_values[key] = value

  identifier = make_id_string(typ, **id_values)

  cache = None
  if identifier in cache_dict:
    cache = cache_dict[identifier]

  if cache is None:
    if create_args is not None:
      kwargs.update(create_args)
    cache = typ(**kwargs)
    cache_dict[identifier] = cache
  elif not isinstance(cache, typ):
    raise ValueError(f"cache entry not of apropriate type: {typ}")
  if hasattr(cache, "is_cache"):
    cache.is_cache = True
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


def print_headlined(headline, config):
  stream = KdStream(outs)

  outs.newlines(3)
  outs.print(headline)
  outs.print("#####################")
  outs.newlines(2)

  stream.print_obj(config)


def copy_attrs(lft, rgt):
  for prop in dir(lft):
    if not prop.startswith("_"):
      setattr(rgt, prop, getattr(lft, prop))



def require_path(path, msg):
  if path is None or not os.path.exists(path):
    raise ValueError(f"{msg}: {path}")




def env_var_or(v, d):
  r = os.getenv(v)
  if r is None:
    return d
  else:
    return r
