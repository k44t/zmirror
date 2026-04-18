import yaml
import pytest

from kpyutils.kiify import yaml_data
from zmirror.dataclasses import ZMirror, ZPool, ZDev, Disk, Part, Crypt, ZVol


def test_yaml_data_name_alias_uses_only_preferred_tag_by_default():
  @yaml_data(name="widget")
  class Widget:
    value: int = 0

  parsed_alias = yaml.full_load("!widget {value: 7}")

  assert isinstance(parsed_alias, Widget)
  assert parsed_alias.value == 7

  with pytest.raises(yaml.constructor.ConstructorError):
    yaml.full_load("!Widget {value: 9}")


def test_yaml_data_name_alias_can_enable_legacy_class_name_tag():
  @yaml_data(name="gadget", also_use_class_name=True)
  class Gadget:
    value: int = 0

  parsed_alias = yaml.full_load("!gadget {value: 7}")
  parsed_legacy = yaml.full_load("!Gadget {value: 9}")

  assert isinstance(parsed_alias, Gadget)
  assert isinstance(parsed_legacy, Gadget)
  assert parsed_alias.value == 7
  assert parsed_legacy.value == 9


def test_zmirror_short_yaml_tags_are_recognized():
  text = """
--- !zmirror
content:
  - !zpool
    name: tank
    content:
      - !zdev
        pool: tank
        name: d1
      - !zvol
        name: data
      - !part
        name: p1
      - !disk
        uuid: 11111111-1111-1111-1111-111111111111
      - !crypt
        name: c1
"""

  config = yaml.full_load(text)

  assert isinstance(config, ZMirror)
  assert isinstance(config.content[0], ZPool)
  assert isinstance(config.content[0].content[0], ZDev)
  assert isinstance(config.content[0].content[1], ZVol)
  assert isinstance(config.content[0].content[2], Part)
  assert isinstance(config.content[0].content[3], Disk)
  assert isinstance(config.content[0].content[4], Crypt)


def test_zmirror_does_not_accept_class_name_yaml_tags_for_short_named_types():
  with pytest.raises(yaml.constructor.ConstructorError):
    yaml.full_load("--- !ZMirror {}")
