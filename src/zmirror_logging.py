
import logging
import logging.handlers
import os
import sys
import inspect

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



LOGFILE_PATH = '/var/lib/zmirror/log.st'

def __init__():
  os.makedirs(os.path.dirname(LOGFILE_PATH), exist_ok = True)


  # Configure the root logger
  logging.basicConfig(
  level=logging.DEBUG,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
  handlers=[
      # logging.FileHandler(logfile_path + datetime.now().strftime("%d-%m-%Y_%H:%M:%S.%f") ),  # File handler
      logging.StreamHandler(sys.stdout)   # Stream handler for stdout
  ]
  )

  logger = logging.getLogger("zmirror")

  # Add systemd journal handler if available
  if USE_JOURNAL:
    journal_handler = JournalHandler()
    journal_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(journal_handler)
  else:
    logging.getLogger().addHandler(logging.handlers.RotatingFileHandler(LOGFILE_PATH, maxBytes=65535))
    logger.warning("systemd log not available")
  return logger


log = __init__()
log.func_start = log_func_start
log.func_end = log_func_end
