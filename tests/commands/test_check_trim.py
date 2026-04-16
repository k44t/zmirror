import argparse
import io

from zmirror.zmirror import make_arg_parser
from zmirror import user_commands


def test_check_trim_parser_wiring():
  parser = make_arg_parser()
  args = parser.parse_args(["check-trim", "sda"])

  assert args.device == "sda"
  assert args.func == user_commands.handle_check_trim_command


def test_enable_trim_parser_wiring():
  parser = make_arg_parser()
  args = parser.parse_args(["enable-trim", "/dev/sda"])

  assert args.device == "/dev/sda"
  assert args.func == user_commands.handle_enable_trim_command


def test_check_trim_prints_command_transcript(monkeypatch):
  calls = []

  def find_provisioning_mode_stub(device):
    assert device == "/dev/sdz"
    return "/sys/block/sdz/device/scsi_disk/0:0:0:0/provisioning_mode"

  def myexec_stub(command, input=None): # pylint: disable=unused-argument,redefined-builtin
    calls.append(command)
    if command.startswith("cat "):
      return 0, ["full"], ["full"], []
    return 0, ["Maximum unmap LBA count: 0x1400000"], ["Maximum unmap LBA count: 0x1400000"], []

  monkeypatch.setattr(user_commands.config, "find_provisioning_mode", find_provisioning_mode_stub)
  monkeypatch.setattr(user_commands, "myexec", myexec_stub)

  output = io.StringIO()
  args = argparse.Namespace(device="sdz", stream=output)

  user_commands.handle_check_trim_command(args)

  text = output.getvalue()
  assert "$ cat /sys/block/sdz/device/scsi_disk/0:0:0:0/provisioning_mode" in text
  assert "stdout: full" in text
  assert "exit code: 0" in text
  assert "$ sg_vpd -a /dev/sdz | grep -i map" in text
  assert "Maximum unmap LBA count: 0x1400000" in text
  assert "device reports TRIM/UNMAP support (Maximum unmap LBA count: 0x1400000) but kernel did not recognize it (mode is `full` instead of `unmap`)." in text
  assert "WARNING: this interpretation is preliminary; zmirror provides no guarantees" in text
  assert calls == [
    "cat /sys/block/sdz/device/scsi_disk/0:0:0:0/provisioning_mode",
    "sg_vpd -a /dev/sdz | grep -i map",
  ]


def test_check_trim_handles_missing_provisioning_path(monkeypatch):
  calls = []

  def myexec_stub(command, input=None): # pylint: disable=unused-argument,redefined-builtin
    calls.append(command)
    return 1, [""], [], ["sg_vpd: command not found"]

  monkeypatch.setattr(user_commands.config, "find_provisioning_mode", lambda _device: None)
  monkeypatch.setattr(user_commands, "myexec", myexec_stub)

  output = io.StringIO()
  args = argparse.Namespace(device="/dev/sda", stream=output)

  user_commands.handle_check_trim_command(args)

  text = output.getvalue()
  assert "provisioning_mode path was not found" in text
  assert "$ sg_vpd -a /dev/sda | grep -i map" in text
  assert "stderr: sg_vpd: command not found" in text
  assert "exit code: 1" in text
  assert "could not evaluate TRIM/UNMAP support from command output" in text
  assert "WARNING: this interpretation is preliminary; zmirror provides no guarantees" in text
  assert calls == ["sg_vpd -a /dev/sda | grep -i map"]


def test_enable_trim_runs_same_force_enable_logic(monkeypatch):
  calls = []
  state = {"mode": "full"}

  def find_provisioning_mode_stub(device):
    assert device == "/dev/sda"
    return "/sys/block/sda/device/scsi_disk/0:0:0:0/provisioning_mode"

  def myexec_stub(command, input=None): # pylint: disable=unused-argument,redefined-builtin
    calls.append(command)
    if command.startswith("cat "):
      return 0, [state["mode"]], [state["mode"]], []
    if command.startswith("echo unmap > "):
      state["mode"] = "unmap"
      return 0, [], [], []
    raise ValueError(f"unexpected command: {command}")

  monkeypatch.setattr(user_commands.config, "find_provisioning_mode", find_provisioning_mode_stub)
  monkeypatch.setattr(user_commands, "myexec", myexec_stub)

  output = io.StringIO()
  args = argparse.Namespace(device="/dev/sda", stream=output)

  user_commands.handle_enable_trim_command(args)

  text = output.getvalue()
  assert "$ cat /sys/block/sda/device/scsi_disk/0:0:0:0/provisioning_mode" in text
  assert "$ echo unmap > /sys/block/sda/device/scsi_disk/0:0:0:0/provisioning_mode" in text
  assert "trim enable command applied; provisioning_mode now reports `unmap`." in text
  assert calls == [
    "cat /sys/block/sda/device/scsi_disk/0:0:0:0/provisioning_mode",
    "echo unmap > /sys/block/sda/device/scsi_disk/0:0:0:0/provisioning_mode",
    "cat /sys/block/sda/device/scsi_disk/0:0:0:0/provisioning_mode",
  ]
