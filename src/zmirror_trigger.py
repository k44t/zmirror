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


from zmirror_logging import log

# Define the path for the Unix socket
socket_path = "/tmp/zmirror_service.socket"

# Create a UDS (Unix Domain Socket)
client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

# Connect the socket to the path where the server is listening
client.connect(socket_path)



try:
    # Send data
    env = dict(os.environ)
    message = json.dumps(env, indent=4)
    print(f"Sending: {message}")
    client.sendall(message.encode('utf-8'))

    # Look for the response
    amount_received = 0
    amount_expected = len(message)
    received_message = ""
    while amount_received < amount_expected:
        data = client.recv(16)
        amount_received += len(data)
        received_message = received_message + data.decode('utf-8')
    if received_message != message:
        log.error("something went wrong on server side, we did not receive back the message that we sent.")

finally:
    print("Closing client")
    client.close()