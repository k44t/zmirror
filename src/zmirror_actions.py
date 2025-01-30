from datetime import datetime
import re
import socket
import os
import threading
import json
from zmirror_logging import log
from zmirror_utils import *
import zmirror_utils as core
import queue

def get_config_actions(text):
  raise NotImplementedError

def handle_offline(entity):
  if hasattr(entity, "handle_offline"):
    entity.handle_offline()

def handle_scrubbed(entity):
  if hasattr(entity, "handle_scrubbed"):
    entity.handle_scrubbed()


def handle_parent_online(child):
  if hasattr(child, "handle_parent_online"):
    child.handle_parent_online()
  else:
    if hasattr(child, "content"):
      for grand_child in child.content:
        handle_parent_online(grand_child)


def handle_parent_offline(child):
  if hasattr(child, "handle_parent_offline"):
    child.handle_parent_offline()
  else:
    if hasattr(child, "content"):
      for grand_child in child.content:
        handle_parent_offline(grand_child)


def handle_entity_online(entity, now: datetime):
  if entity.state.what != Entity_State.ONLINE:
    entity.state = Since(Entity_State.ONLINE, now)
    id = entity_id(entity)
    config = load_config_for_id(id)
    if config != None:
      for child in config.content:
        handle_parent_online(child)

def handle_entity_offline(entity, now: datetime):
  if entity.state.what != Entity_State.DISCONNECTED:
    entity.state = Since(Entity_State.DISCONNECTED, now)
    entity.last_online = now
    id = entity_id(entity)
    config = load_config_for_id(id)
    if config != None:
      for child in config.content:
        handle_parent_offline(child)