from datetime import datetime

from zmirror_dataclasses import EntityState, set_entity_state, is_offline
from zmirror_utils import load_config_for_cache
import zmirror_utils as core


def get_config_actions(text):
  raise NotImplementedError

def handle_scrubbed(entity):
  if hasattr(entity, "handle_scrubbed"):
    entity.handle_scrubbed()


def handle_parent_online(parent, child):
  if hasattr(child, "handle_parent_online"):
    child.handle_parent_online()
  else:
    if hasattr(child, "content"):
      for grand_child in child.content:
        handle_parent_online(child, grand_child)


def handle_parent_offline(parent, child):
  if hasattr(child, "handle_parent_offline"):
    child.handle_parent_offline()
  else:
    if hasattr(child, "content"):
      for grand_child in child.content:
        handle_parent_offline(child, grand_child)


def handle_child_online(parent):
  if hasattr(parent, "handle_child_online"):
    parent.handle_child_online()



def handle_child_offline(parent):
  if hasattr(parent, "handle_child_offline"):
    parent.handle_child_offline()


# updates the entity cache info as it comes online
# triggers child actions
# triggers parrent actions
def handle_entity_online(entity, now: datetime):
  if entity.state.what != EntityState.ONLINE:
    set_entity_state(entity, EntityState.ONLINE)
    config = load_config_for_cache(entity)
    if config is not None:
      for child in config.content:
        handle_parent_online(config, child)
      if hasattr(config, "parent") and config.parent is not None:
        handle_child_online(config.parent)

# updates the entity cache info as it goes offline
# triggers child actions
# triggers parent actions
def handle_entity_offline(entity, now: datetime):
  if entity.state.what != EntityState.DISCONNECTED:
    set_entity_state(entity, EntityState.DISCONNECTED)
    config = load_config_for_cache(entity)
    if config is not None:
      for child in config.content:
        handle_parent_offline(config, child)
      if hasattr(config, "parent") and config.parent is not None:
        handle_child_offline(config.parent)
