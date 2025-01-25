
import logging
import logging.handlers
import os
from datetime import datetime
import sys



def __init__():
  logfile_path = '/var/run/zmirror/log.st'
  os.makedirs(os.path.dirname(logfile_path), exist_ok = True)
  
  # Check if systemd is available
  try:
    from systemd.journal import JournalHandler
    use_journal = True
  except ImportError:
    use_journal = False

  # Configure the root logger
  logging.basicConfig(
  level=logging.DEBUG,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
  handlers=[
      logging.FileHandler(logfile_path + datetime.now().strftime("%d-%m-%Y_%H:%M:%S.%f") ),  # File handler
      logging.StreamHandler(sys.stdout)   # Stream handler for stdout
  ]
  )

  log = logging.getLogger("zmirror")

  # Add systemd journal handler if available
  if use_journal:
    journal_handler = JournalHandler()
    journal_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(journal_handler)
  else:
    logging.getLogger().addHandler(logging.handlers.RotatingFileHandler(logfile_path, maxBytes=65535))
    log.warning("systemd log not available")
  return log


log = __init__()