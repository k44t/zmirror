
#pylint: disable=unsubscriptable-object
#pylint: disable=not-an-iterable
#pylint: disable=invalid-field-call
#pylint: disable=no-member
#pylint: disable=unsupported-membership-test
#pylint: disable=useless-parent-delegation.html
#pylint: disable=no-else-return
#pylint: disable=abstract-method.html


from datetime import datetime
from dataclasses import dataclass, field
from typing import Any
from .util import read_file
from enum import Enum
import random
import sys

import dateparser

from kpyutils.kiify import yaml_data, yaml_enum, KiEnum, KdStream, yes_no_absent_or_dict



from .logging import log
from . import commands as commands
from . import config as config
from .config import iterate_content_tree3_depth_first


class Reason(KiEnum):
  DEPENDENCY_CANCELLED = 0
  DEPENDENCY_FAILED = 1
  TIMEOUT = 2
  DEPENDENT_FAILED = 3
  DEPENDENT_CANCELLED = 4
  DEPENDENT_SUCCEEDED = 5
  USER_REQUESTED = 6
  MUST_BE_DONE_MANUALLY = 7
  NOT_SUPPORTED_FOR_ENTITY_TYPE = 8
  STATE_DOES_NOT_ALLOW_REQUEST = 9
  TOO_MANY_RAID_DEPENDENCIES_FAILED = 10
  ALL_MIRROR_DEPENDENCIES_FAILED = 11
  NO_LONGER_REQUIRED = 12
  COMMAND_FAILED = 13
  # for cancelling a request
  REPLACING_REQUEST = 14
  BELOW_ENACTMENT_LEVEL = 15



last_enactment_id = 0

def next_enactment_id():
  global last_enactment_id
  if last_enactment_id == sys.maxsize:
    last_enactment_id = 0
  else:
    last_enactment_id += 1
  return last_enactment_id


@yaml_enum
class RequestType(KiEnum):

  OFFLINE = 0

  ONLINE = 1

  SCRUB = 2

  TRIM = 3

  APPEAR = 7


  CANCEL_SCRUB = 4

  CANCEL_TRIM = 5

  SNAPSHOT = 6

  # online request that does not online the corresponding pool
  ONLINE_IF_POOL = 8

  def opposite(self):
    if self == RequestType.ONLINE:
      return RequestType.OFFLINE
    return RequestType.ONLINE


@dataclass
class Request:
  request_type: RequestType
  entity: Any
  enactment_level: int

  depending_on: list = field(default_factory=list)
  depended_by: list = field(default_factory=list)

  

  # enacted, failed or cancelled.
  handled = False

  # whether the command was already issued and cannot be issued again. 
  # possibly set by the entity
  enacted = False

  # succeeded
  succeeded = False


  # all necessary dependencies succeeded
  dependencies_succeeded = False

  cancel_on_last_dependent_stop = False

  enactment_id = None

  def cancel(self, reason: Reason, cancel_dependencies=False):
    if not self.handled:
      self.stop0("cancelled", reason)
      for d in self.depending_on.copy():
        d.dependent_cancelled(self, cancel_dependencies)
      for d in self.depended_by.copy():
        d.dependency_cancelled(self)
      self.stop99()

  def stop0(self, stop_mode, reason: Reason = None):
    self.handled = True
    log.info(f"{config.human_readable_id(self.entity)}: request {self.request_type.name} {stop_mode}{f" because {reason.name}" if reason else ""}")
    
  def stop99(self):
    self.depending_on = []
    self.depended_by = []
    self.entity.requested.pop(self.request_type)

  def fail(self, reason: Reason):
    if not self.handled:
      self.stop0("failed", reason)
      for d in self.depending_on.copy():
        d.dependent_failed(self)
      for d in self.depended_by.copy():
        d.dependency_failed(self)
      self.stop99()


  def succeed(self):
    if not self.handled:
      self.stop0("succeeded")
      self.succeeded = True
      for d in self.depending_on.copy():
        d.dependent_succeeded(self)
      for d in self.depended_by.copy():
        d.dependency_succeeded(self)
      self.stop99()
  

  def check_dependencies(self):
    for d in self.depending_on:
      if not d.handled:
        return False
      elif not d.succeeded:
        self.fail(Reason.DEPENDENCY_FAILED)
        return False
    return True


  def dependency_stop(self, _dep):
    if not self.handled:
      self.enact()

  def dependent_stop(self, dep, cancel_requested=False):
    if not self.handled:
      self.depended_by.remove(dep)
      if cancel_requested:
        self.cancel(Reason.USER_REQUESTED)
      elif not self.depended_by and self.cancel_on_last_dependent_stop:
        self.cancel(Reason.NO_LONGER_REQUIRED)
  
  def dependent_failed(self, dep):
    self.dependent_stop(dep)

  def dependent_succeeded(self, dep):
    self.dependent_stop(dep)

  def dependency_succeeded(self, dep):
    self.dependency_stop(dep)
  
  def dependency_failed(self, dep):
    self.dependency_stop(dep)
  
  def dependency_cancelled(self, dep):
    self.dependency_stop(dep)

  def dependent_cancelled(self, dep, cancel_requested=False):
    if cancel_requested:
      self.dependent_stop(dep, cancel_requested)

  def enact_hierarchy(self, enactment_id=None):
    if not self.handled:

      # enactment_id keeps us from going into infinite recursion
      if enactment_id is None:
        enactment_id = next_enactment_id()
      
      if self.enactment_id == enactment_id:
        return
      self.enactment_id = enactment_id

      for d in self.depending_on.copy():
        d.enact_hierarchy(enactment_id)
      self.enactment_id = None
      self.enact()

  def set_enacted(self):
    self.enacted = True

  def enact(self):
    if not self.handled:
      if self.entity.is_fulfilled(self):
        self.succeed()
      else:
        if self.check_dependencies():
          unsupported = self.entity.unsupported_request(self.request_type)
          if unsupported:
            self.fail(unsupported)
          else:
            if self.enactment_level >= 0:
                if self.entity.state_allows(self.request_type):
                  # this is checked only here, because at this point something
                  # must be done at the entity itself to fulfill the request
                  # while up to this point the request might have been fulfilled
                  # by bringing online the parent
                  #
                  # maybe this is not necessary at all though.
                  if not self.enacted:
                    self.entity.enact(self)
            else:
              self.fail(Reason.BELOW_ENACTMENT_LEVEL)


  def add_dependency(self, dependency):
    if not self.handled:
      self.depending_on.append(dependency)
      dependency.depended_by.append(self)

@dataclass
class MirrorRequest(Request):
  """for this request to succeed at least one dependency must succeed"""

  def check_dependencies(self):
    # all_failed will be true unless one dependency has not been handled yet
    # and it will be ignored if one dependency has succeeded
    one_succeeded = False
    for d in self.depending_on:
      if not d.handled:
        # a mirror request can only succeed once all its child requests have either 
        # failed or succeeded. This is to prevent the pool from coming online while
        # some zdevs are still being decrypted.
        return False
      if d.succeeded:
        one_succeeded = True
    if one_succeeded:
      return True
    else:
      self.fail(Reason.ALL_MIRROR_DEPENDENCIES_FAILED)
      return False

@dataclass
class RaidRequest(Request):
  """for this request to succeed at least num_of_dependencies - parity must succeed"""
  parity: int = None

  def check_dependencies(self):
    num_succeeded = 0
    for d in self.depending_on:
      if not d.handled:
        # this request will only succeed once all dependent requests have been handled
        return False
      if d.succeeded:
        num_succeeded += 1
    
    num_total = len(self.depending_on)
    num_required = num_total - self.parity
    
    # once the parity has been reached the request has been fulfilled
    if num_succeeded >= num_required:
      return True
    else:
      self.fail(Reason.TOO_MANY_RAID_DEPENDENCIES_FAILED)
      return False

