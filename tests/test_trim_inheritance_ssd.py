from zmirror import config
from zmirror.dataclasses import ZMirror, Disk, Part, ZDev, effective_unpluggable


def wire_chain(root_ssd=True, disk_ssd=None, root_trim="1 week", zdev_trim=None):
  root = ZMirror()
  root.ssd = root_ssd
  root.trim_interval = root_trim
  root.scrub_interval = "4 weeks"
  root.update_interval = "2 weeks"

  disk = Disk()
  disk.uuid = "disk-uuid"
  disk.ssd = disk_ssd
  disk.parent = root

  part = Part()
  part.name = "part-a"
  part.parent = disk

  zdev = ZDev()
  zdev.pool = "tank"
  zdev.name = "dev-a"
  zdev.parent = part
  zdev.trim_interval = zdev_trim

  return root, disk, zdev


def test_zdev_does_not_inherit_trim_interval_when_disk_unset_and_root_ssd_false():
  original_root = config.config_root
  try:
    root, _disk, zdev = wire_chain(root_ssd=False, disk_ssd=None, root_trim="10 days")
    config.config_root = root

    zdev.finalize_init()

    assert zdev.trim_interval is None
  finally:
    config.config_root = original_root


def test_zdev_inherits_trim_interval_when_disk_ssd_true():
  original_root = config.config_root
  try:
    root, disk, zdev = wire_chain(root_ssd=False, disk_ssd=True, root_trim="10 days")
    config.config_root = root

    zdev.finalize_init()

    assert zdev.trim_interval == "10 days"
  finally:
    config.config_root = original_root


def test_zdev_does_not_inherit_trim_interval_when_disk_ssd_false():
  original_root = config.config_root
  try:
    root, disk, zdev = wire_chain(root_ssd=True, disk_ssd=False, root_trim="10 days")
    config.config_root = root

    zdev.finalize_init()

    assert zdev.trim_interval is None
  finally:
    config.config_root = original_root


def test_explicit_zdev_trim_interval_overrides_ssd_inheritance_gate():
  original_root = config.config_root
  try:
    root, disk, zdev = wire_chain(root_ssd=False, disk_ssd=False, root_trim="10 days", zdev_trim="3 days")
    config.config_root = root

    zdev.finalize_init()

    assert zdev.trim_interval == "3 days"
  finally:
    config.config_root = original_root


def test_scrub_interval_inheritance_is_unchanged_by_ssd_gate():
  original_root = config.config_root
  try:
    root, disk, zdev = wire_chain(root_ssd=False, disk_ssd=False, root_trim="10 days")
    config.config_root = root

    zdev.finalize_init()

    assert zdev.scrub_interval == "4 weeks"
  finally:
    config.config_root = original_root


def test_unpluggable_inherits_from_root_to_child_entities():
  original_root = config.config_root
  try:
    root, disk, zdev = wire_chain()
    root.unpluggable = True
    config.config_root = root

    assert effective_unpluggable(disk) is True
    assert effective_unpluggable(zdev) is True
  finally:
    config.config_root = original_root
