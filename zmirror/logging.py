
import logging
from logging import addLevelName
import logging.handlers
import os
import sys
import inspect
import traceback
import re

# Check if systemd is available
try:
  from systemd.journal import JournalHandler
  USE_JOURNAL = True
except ImportError:
  USE_JOURNAL = False

def log_func_start():
  frame = inspect.currentframe().f_back
  function_qualifier_name = frame.f_code.co_qualname
  message = function_qualifier_name + " start"
  log.info(message)

def log_func_end():
  frame = inspect.currentframe().f_back
  function_qualifier_name = frame.f_code.co_qualname
  message = function_qualifier_name + " end"
  log.info(message)



VERBOSE = 15
TRACE = 5



# LOGFILE_PATH = '/var/lib/zmirror/log.st'

def __init__():


  # Configure the root logger
  logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)7s: %(message)s',
    handlers=[
        # logging.FileHandler(logfile_path + datetime.now().strftime("%d-%m-%Y_%H:%M:%S.%f") ),  # File handler
        logging.StreamHandler(sys.stdout)   # Stream handler for stdout
    ]
  )

  logger = logging.getLogger("zmirror")
  logger = logging.LoggerAdapter(logger, {'SYSLOG_IDENTIFIER': "zmirror"})

  def addHandler(handler):
    return logger.logger.addHandler(handler)
  def removeHandler(handler):
    return logger.logger.removeHandler(handler)
  logger.addHandler = addHandler
  logger.removeHandler = removeHandler


  # Add systemd journal handler if available
  if USE_JOURNAL:
    journal_handler = JournalHandler()
    formatter = logging.Formatter('%(levelname)7s: %(message)s')
    journal_handler.setFormatter(formatter)
    logging.getLogger().addHandler(journal_handler)
  if not USE_JOURNAL:
    logger.warning("systemd log not available")

  logger.original_error = logger.error
  logger.original_info = logger.info
  logger.original_debug = logger.debug
  logger.original_warning = logger.warning
  logger.original_critical = logger.critical
  def customized_logger(level, message, *args, **kwargs):
    if logger.getEffectiveLevel() <= logging.DEBUG:
      message = str(message)
      callstack = ""
      raw_tb = traceback.extract_stack()
      entries = traceback.format_list(raw_tb)
      for line in entries:
          if ".vscode-server" in line or "/nix/store/" in line or "Apoeschllogging.py" in line\
            or "zmirror_logging.py" in line:
              continue
          else:
              # regexp_pattern = r'line (.*?),'
              # line_number = re.search(regexp_pattern, line).group(1)
              # #line_number = clicolors.DEBUG + line_number + clicolors.OKBLUE
              # regexp_pattern = r'File "(.*?)"'
              # file = re.search(regexp_pattern, line).group(1)
              # regexp_pattern = r'in (.*?)\n'
              # function = re.search(regexp_pattern, line).group(1)
              # if function == "<module>":
              #     callstack = callstack + file + ":" + line_number + ":" + function
              # else:
              #     callstack = callstack + "->" + file + ":" + line_number + ":" + function

              regexp_pattern = r'File "(.*?)".+line (.*?),.+in (.*?)\n'
              match = re.search(regexp_pattern, line)
              if match:
                function = match.group(3)
                if function == "<module>":
                  callstack = callstack + match.group(1) + ":" + match.group(2) + ":" + function
                else:
                  callstack = callstack + "->" + match.group(1) + ":" + match.group(2) + ":" + function
      modified_message = message + '\033[90m' + "     <<<<<<<<< " + callstack + '\033[0m'
    else:
      modified_message = message
    if level == logging.ERROR:
        logger.original_error(modified_message, *args, **kwargs)
    elif level == logging.INFO:
        logger.original_info(modified_message, *args, **kwargs)
    elif level == logging.DEBUG:
        logger.original_debug(modified_message, *args, **kwargs)
    elif level == logging.WARNING:
        logger.original_warning(modified_message, *args, **kwargs)
    elif level == logging.CRITICAL:
        logger.original_critical(modified_message, *args, **kwargs)
  def customized_error(message, *args, **kwargs):
    customized_logger(logging.ERROR, message, *args, **kwargs)
  def customized_info(message, *args, **kwargs):
    customized_logger(logging.INFO, message, *args, **kwargs)
  def customized_debug(message, *args, **kwargs):
    customized_logger(logging.DEBUG, message, *args, **kwargs)
  def customized_warning(message, *args, **kwargs):
    customized_logger(logging.WARNING, message, *args, **kwargs)
  def customized_critical(message, *args, **kwargs):
    customized_logger(logging.CRITICAL, message, *args, **kwargs)

  logger.error = customized_error
  logger.info = customized_info
  logger.debug = customized_debug
  logger.warning = customized_warning
  logger.critical = customized_critical

  def verbose(msg, *args, **kwargs):
    """
    Delegate a debug call to the underlying logger.
    """
    logger.log(VERBOSE, msg, *args, **kwargs)
  logger.verbose = verbose

  def trace(msg, *args, **kwargs):
    """
    Delegate a debug call to the underlying logger.
    """
    logger.log(TRACE, msg, *args, **kwargs)
  logger.trace = trace





  return logger


addLevelName(VERBOSE, "VERBOSE")
addLevelName(TRACE, "TRACE")

log = __init__()
log.func_start = log_func_start
log.func_end = log_func_end
