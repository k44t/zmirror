from datetime import datetime

from zmirror_dataclasses import EntityState, Since
from zmirror_utils import load_config_for_id, entity_id


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


def handle_child_online(parent, child):
  pass


def handle_child_offline(parent, child):
  pass

# updates the entity cache info as it comes online
# triggers child actions
# triggers parrent actions
def handle_entity_online(entity, now: datetime):
  if entity.state.what != EntityState.ONLINE:
    entity.state = Since(EntityState.ONLINE, now)
    identifier = entity_id(entity)
    config = load_config_for_id(identifier)
    if config is not None:
      for child in config.content:
        handle_parent_online(config, child)
      if hasattr(config, "parent") and config.parent is not None:
        handle_child_online(config.parent, config)

# updates the entity cache info as it goes offline
# triggers child actions
# triggers parent actions
def handle_entity_offline(entity, now: datetime):
  if entity.state.what != EntityState.DISCONNECTED:
    entity.state = Since(EntityState.DISCONNECTED, now)
    entity.last_online = now
    identifier = entity_id(entity)
    config = load_config_for_id(identifier)
    if config is not None:
      for child in config.content:
        handle_parent_offline(config, child)
      if hasattr(config, "parent") and config.parent is not None:
        handle_child_offline(config.parent, config)

