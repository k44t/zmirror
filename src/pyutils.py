from datetime import datetime, timedelta
import os
import subprocess
import sys
from zmirror_logging import ZMirror_Logger
from ki_utils import *

zmirror_logger = ZMirror_Logger()
log = zmirror_logger.get_Logger()

def myexec(command):
    log.info(f"Executing command: {command}")
    process = subprocess.Popen(command,
                               shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    formatted_output = []
    formatted_response = []
    formatted_error = []
    # set blocking to not blocking is necessary so that readline wont block when the process already finished. this only works on linux systems!
    os.set_blocking(process.stdout.fileno(), False)
    os.set_blocking(process.stderr.fileno(), False)
    try:
        timestamp_last_stdout_readline_start = datetime.now()
        timestamp_last_stderr_readline_start = datetime.now()
        timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
        timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
        while process.poll() is None:
            if process.stdout != None:
                response_line = process.stdout.readline().decode("utf-8").replace("\n", "")
                if response_line != "":
                    log.info("stdout: " + response_line)
                if response_line != "":
                    timestamp_last_stdout_readline_start = datetime.now()
                    timestamp_last_stdout_readline = timestamp_last_stdout_readline_start
                    timestamp_last_stderr_readline = datetime.now()
            if process.stderr != None:
                error_line = process.stderr.readline().decode("utf-8").replace("\n", "")
                if error_line != "":
                    log.error("stderr: " + error_line)
                if error_line != "":
                    timestamp_last_stderr_readline_start = datetime.now()
                    timestamp_last_stderr_readline = timestamp_last_stderr_readline_start
                    timestamp_last_stdout_readline = datetime.now()
            if (process.stderr != None and error_line == "") and (process.stdout != None and response_line == ""):
                timestamp_stdout_now = datetime.now()
                timestamp_stderr_now = datetime.now()
                if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)) and \
                        timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
                    no_output_since = min(timestamp_stderr_now - timestamp_last_stderr_readline_start,
                                          timestamp_stdout_now - timestamp_last_stdout_readline_start)
                    log.warning(f"Command `{command}` had no stderr and stdout output since {no_output_since}.")
                    timestamp_last_stdout_readline = timestamp_stdout_now
                    timestamp_last_stderr_readline = timestamp_stderr_now
            elif (process.stderr != None and error_line == ""):
                timestamp_stderr_now = datetime.now()
                if timestamp_stderr_now > (timestamp_last_stderr_readline + timedelta(seconds=5)):
                    log.warning(f"Command `{command}` had no stderr output since {timestamp_stderr_now - timestamp_last_stderr_readline_start}.")
                    timestamp_last_stderr_readline = timestamp_stderr_now
            elif (process.stdout != None and response_line == ""):
                timestamp_stdout_now = datetime.now()
                if timestamp_stdout_now > (timestamp_last_stdout_readline + timedelta(seconds=5)):
                    log.warning(f"Command `{command}` had no stdout output since {timestamp_stdout_now - timestamp_last_stdout_readline_start}.")
                    timestamp_last_stdout_readline = timestamp_stdout_now
            if response_line != "":
                formatted_response.append(response_line)
                formatted_output.append(response_line)
            if error_line != "":
                formatted_error.append(error_line)
                formatted_output.append(error_line)
    except Exception as e:
        pass
    try:
        response = process.stdout.readlines()
        for line in response:
            line = line.decode("utf-8").replace("\n", "")
            if line != "":
                log.info("stdout: " + line)
                formatted_response.append(line)
                formatted_output.append(line)
    except Exception as e:
        pass
    try:
        error = process.stderr.readlines()
        for line in error:
            line = line.decode("utf-8").replace("\n", "")
            if line != "":
                log.error("stderr: " + line)
                formatted_error.append(line)
                formatted_output.append(line)
    except Exception as e:
        pass
    return process.returncode, formatted_output, formatted_response, formatted_error

def load_yaml_cache(cache_file_path):
  try:
    with open(cache_file_path) as stream:
        cache_dict = yaml.full_load(stream)
        if not isinstance(cache_dict, dict):
          cache_dict = dict()
  except BaseException as exception:
    log.error(exception)
    cache_dict = dict()
  return cache_dict

def find_or_create_cache(cache_dict, type, create_args=dict(), **kwargs):
  id = type.__class__.__name__
  for i, (key, value) in enumerate(kwargs.items()):
    id = id + "|" + value

  cache = None
  if id in cache_dict:
    cache = cache_dict[id]

  if not isinstance(cache, type):
    kwargs.update(create_args)
    cache = type(**kwargs)
    cache_dict[id] = cache
  return cache

def log_env(env):
  stream = Tabbed_Shiftex_Stream(sys.stdout)
  for var in env:
    if not var.startswith("_"):
      stream.print_raw(f"{var}:: ")
      stream.indent()
      stream.print_indented(env[var])
      stream.dedent()

def load_yaml_config(config_file_path):
  with open(config_file_path) as config_file:
    config = yaml.full_load(config_file)
    return config

outs = Tabbed_Shiftex_Stream(sys.stdout)

def print_config(config):
    stream = Kd_Stream(outs)

    outs.newlines(3)
    outs.print("config")
    outs.print("#####################")
    outs.newlines(2)

    stream.print_obj(config)

def remove_cache(cache_file_path):
  log.info(f"removing {cache_file_path}")
  try:
    os.remove(cache_file_path)
  except Exception as exception:
    log.error(f"failed to remove {cache_file_path}. " + str(exception))

def save_cache(cache_dict, cache_file_path):
  log.info("writing cache")
  with open(cache_file_path, 'w') as stream:
    yaml.dump(cache_dict, stream)

def copy_attrs(lft, rgt):
  for prop in dir(lft):
    if not prop.startswith("_"):
      setattr(rgt, prop, getattr(lft, prop))