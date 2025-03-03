from pyutils import myexec as exec#pylint: disable=redefined-builtin
from zmirror_logging import log



commands = []

def add_command(command):
  commands.append(command)


def execute_commands():
  seen = set()                                                    
  cmds = [x for x in commands if not (x in seen or seen.add(x))]

  for cmd in cmds:
    _execute_command(cmd)

def _execute_command(command):
  apply_commands = False
  if apply_commands:
    log.info(f"executing command: {command}")
    returncode, formatted_output, _, _ = exec(command)#pylint: disable=exec-used
    if returncode != 0:
      currently_scrubbing = False
      for line in formatted_output:
        if "currently scrubbing" in line:
          info_message = line
          log.info(info_message)
          currently_scrubbing = True
      if not currently_scrubbing:
        error_message = f"something went wrong while executing command {command}, terminating script now"
        log.error(error_message)
        exit(error_message)
    log.info(formatted_output)
  else:
    warning_message = f"applying command '{command}' is currently turned off!"
    log.warning(warning_message)
