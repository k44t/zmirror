# handle's events from the zfs event daemon
# by being simply called by it
# is invoked by a little shell script /etc/zfs/zed.d/all-zmirror.sh
# uses environment variables given by the zfs event daemon
# connects to a unix socket
# sends all relevant environment variables for the event through the socket as a simple jsonfied dictionary
# uses the same way of logging and output as zmirror core
import socket
import json
import os
import sys

from .util import require_path
from .defaults import *

# Define the path for the Unix socket
path = os.getenv("ZMIRROR_SOCKET_PATH")
if path is None or len(sys.argv) > 1:
  import argparse
  parser = argparse.ArgumentParser(prog="zmirror-trigger")
  # parser.add_argument('--version', de='version', version=f'zmirror-trigger {get_version()}')
  parser.add_argument("--socket-path", type=str, help="the path to the unix socket (used by zmirror.trigger)", default=ZMIRROR_SOCKET_PATH_DEFAULT)
  args = parser.parse_args()
  path = args.socket_path

require_path(path, "no zmirror socket at")

# Create a UDS (Unix Domain Socket)
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as con:

  try:
    # Connect the socket to the path where the server is listening
    con.connect(path)



    # Send data
    env = dict(os.environ)
    message = json.dumps(env).encode('utf-8')
    con.sendall(f"{len(message)}:".encode('utf-8') + message)
  except Exception as ex:
    print(f"error while sending data to zmirror-daemon: {ex}")