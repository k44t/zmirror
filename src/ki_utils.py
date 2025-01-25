from dataclasses import dataclass
from datetime import datetime
import numbers
from typing import List
import yaml
from io import StringIO
from enum import Enum

from zmirror_logging import ZMirror_Logger
zmirror_logger = ZMirror_Logger()
log = zmirror_logger.get_Logger()

def convert_dict_to_strutex(dictionary):
  for key, value in dictionary.items():
    result_string = result_string + f"\n\t{key}:: {value}"
  return result_string

def ki_to_bool(v):
  if isinstance(v, bool):
    return v
  elif v == "yes":
    return True
  elif v == "no":
    return False
  else:
    raise BaseException("not a ki boolean")


def escape_ki_string(delim, string):
  index = 0
  l = len(string) - 1
  result = StringBuilder()
  fn = escape_ki_string_normal
  extra = ""
  while True:
    if index > l:
      if False and len(extra) > 0:
        if extra[0] == "\"":
          result.append("\\")
          result.append(extra)
        else:
          result.append(extra)
          result.append(extra[0])
      break
    fn, index, extra = fn(result, string, index, delim, extra)
  return str(result)

def escape_ki_string_backslash(result, string, index, delim, backslashes):
  if string[index] == "\\":
    return escape_ki_string_backslash,  index + 1, backslashes.append("\\")
  else:
    result.append("\\")
    result.append(str(backslashes))
    return escape_ki_string_normal,  index, StringBuilder()


def escape_ki_string_dollar(result, string, index, delim, dollars):
  if string[index] == "$":
    return escape_ki_string_dollar,  index + 1, dollars.append("$")
  else:
    result.append("\\")
    result.append(str(dollars))

    return escape_ki_string_normal, index, StringBuilder()

def escape_ki_string_delim(result, string, index, delim, quotes):
  if string[index] == delim:
    return escape_ki_string_delim, index + 1, quotes.append("\"")
  else:
    result.append("\\")
    result.append(str(quotes))

    return escape_ki_string_normal,   index, StringBuilder()


def escape_ki_string_normal(result, string, index, delim, ignoreme):
  # print("startresult: ", result)
  c = string[index]
  if c == "\\":
    return escape_ki_string_backslash,   index + 1, StringBuilder().append(c)
  elif c == "$":
    return escape_ki_string_dollar,  index + 1, StringBuilder().append(c)
  elif c == "\"":
    return escape_ki_string_delim, index + 1, StringBuilder().append(c)
  else:
    result.append(c)
    return escape_ki_string_normal, index + 1, StringBuilder()
  
class StringBuilder:
  _file_str = None

  def __init__(self):
    self._file_str = StringIO()
    self.string = ""

  def append(self, str):
    self._file_str.write(str)
    return self

  def __str__(self):
    return self._file_str.getvalue()

  def write(self, text):
    self.string = self.string + text
  
  def get_string(self):
    return_string = self.string
    self.string = ""
    return return_string














#sys.stdout.write("escaped: '")
#sys.stdout.write(escape_ki_string('"', 'hello \\\\\\\\ $$$$ """" World!'))
#sys.stdout.write("'")
#exit()




class Ki_Enum(Enum):

  def __to_kd__(self, ki_stream):
    ki_stream.stream.print_raw("#" + self.name.lower().replace("_", "-"))



class Tabbed_Shiftex_Stream():
  def __init__(self, stream, indents = 0):
    self.indents = indents
    self.stream = stream

  def indent(self):
    self.indents = self.indents + 1

  def dedent(self):
    self.indents = self.indents - 1


  def newline(self):
    self.print_raw("\n")
    for i in range(0, self.indents):
        self.print_raw("  ")

  def newlines(self, num):
    for _ in range(0, num):
      self.newline()


  def print(self, string):
    for i, line in enumerate(string.splitlines()):
      if i > 0:
        self.newline()
      self.print_raw(line)


  def print_raw(self, string):
    self.stream.write(string)

class Kd_Stream:
  def __init__(self, stream, level = -1):
    self.stream = stream
    self.level = level

  def print_obj(self, obj):
    if self.level == 0:
      self.stream.print_raw("...\n")
      return
    self.level = self.level - 1
    if isinstance(obj, bool):
      if obj:
        self.stream.print_raw("yes")
      else:
        self.stream.print_raw("no")
    elif isinstance(obj, str):
      self.stream.print_raw("\"")
      for i, line in enumerate(obj.split('\n')):
        if i > 0:
          self.newline()
        self.stream.print_raw(escape_ki_string('"', line))
        # self.stream.print_raw(line)
      self.stream.print_raw("\"")
    elif isinstance(obj, numbers.Number):
      self.stream.print_raw(str(obj))
    elif isinstance(obj, datetime):
      self.stream.print_raw(obj.strftime("%Y-%m-%d'%H:%M:%S.%f"))
    elif isinstance(obj, list):
      self.stream.print_raw("[:")
      self.stream.indent()
      for i, element in enumerate(obj):
        # self.stream.print_raw("||")
        self.stream.newline()
        # self.stream.print_raw(">>")
        self.print_obj(element)
        # self.stream.print_raw("<<")
      self.stream.dedent()
    elif isinstance(obj, dict):
      self.stream.print_raw("{:")
      self.stream.indent()
      for i, (key, value) in enumerate(obj.items()):
        self.stream.newline()
        self.print_obj(key)
        self.stream.print_raw(":")
        self.stream.indent()
        self.print_obj(value)
        self.stream.dedent()
      self.stream.dedent()
    elif obj == None:
      self.stream.print_raw("nil")
    elif hasattr(obj, "__to_kd__") and callable(obj.__to_kd__):
      obj.__to_kd__(self)
    else:
      self.print_python_obj(obj)

    self.level = self.level + 1



  def print_python_obj(self, obj):
    attrs = dir(obj)
    nattrs = []
    for attr in attrs:
      if not (attr.startswith("_") or callable(getattr(obj, attr))):
        nattrs.append(attr)
    self.print_partial_obj(obj, nattrs)

  def print_partial_obj(self, obj, props: List[str]):
    if self.level == 0:
      self.stream.print_raw("...")
      return
    self.stream.print_raw(obj.__class__.__name__)
    self.stream.indent()
    if len(props) > 0:
      for prop in props:
        if hasattr(obj, prop):
          # self.stream.print_raw("..nl>")
          self.stream.newline()
          # self.stream.print_raw("..<nl")

          # self.stream.print_raw("..>>")
          self.stream.print_raw(prop)
          self.stream.print_raw(": ")
          if callable(getattr(obj, prop)):
            self.stream.print_raw("fn ...")
          else:
            # self.stream.print_raw("|||")
            self.print_obj(getattr(obj, prop))
            # self.stream.print_raw("<<..")
    else:
      self.stream.print_raw("!")
    self.stream.dedent()

  def get_string_from_object(self, obj):
    if isinstance(self.stream, StringBuilder):
      self.print_obj(obj)
      return self.stream.stream.get_string()
    else:
      error_message = "get_string_from_object is not implemented for anything other than a stream of type StringBuilder"
      log.error(error_message)
      raise NotImplementedError(error_message)

  def get_object_from_string(self, string):
    if self.level == 0:
      self.stream.print_raw("...\n")
      return
    self.level = self.level - 1
    if isinstance(obj, bool):
      if obj:
        self.stream.print_raw("yes")
      else:
        self.stream.print_raw("no")
    elif isinstance(obj, str):
      self.stream.print_raw("\"")
      for i, line in enumerate(obj.split('\n')):
        if i > 0:
          self.newline()
        self.stream.print_raw(escape_ki_string('"', line))
        # self.stream.print_raw(line)
      self.stream.print_raw("\"")
    elif isinstance(obj, numbers.Number):
      self.stream.print_raw(str(obj))
    elif isinstance(obj, datetime):
      self.stream.print_raw(obj.strftime("%Y-%m-%d'%H:%M:%S.%f"))
    elif isinstance(obj, list):
      self.stream.print_raw("[:")
      self.stream.indent()
      for i, element in enumerate(obj):
        # self.stream.print_raw("||")
        self.stream.newline()
        # self.stream.print_raw(">>")
        self.print_obj(element)
        # self.stream.print_raw("<<")
      self.stream.dedent()
    elif isinstance(obj, dict):
      self.stream.print_raw("{:")
      self.stream.indent()
      for i, (key, value) in enumerate(obj.items()):
        self.stream.newline()
        self.print_obj(key)
        self.stream.print_raw(":")
        self.stream.indent()
        self.print_obj(value)
        self.stream.dedent()
      self.stream.dedent()
    elif obj == None:
      self.stream.print_raw("nil")
    elif hasattr(obj, "__to_kd__") and callable(obj.__to_kd__):
      obj.__to_kd__(self)
    else:
      self.print_python_obj(obj)

    self.level = self.level + 1


def to_ki_enum(data: Enum):
  return "#" + data.name.lower().replace("_", "-")

def from_ki_enum(cls, string: str):
  fixed = string.removeprefix("#").upper().replace("-", "_")
  r = cls[fixed]
  if r == None:
    raise BaseException(f"`{string}` (`{fixed}`) is not an instance of {cls.__class__.__name__}")
  return r


def yaml_enum(cls):
  # Perform operations using the class name
  # print(f"Decorating class: {cls.__name__}")

  # You can add attributes or methods to the class if needed
  # cls.decorated = True

  tag = u"!" + cls.__name__

  def the_constr(loader, node):
    # https://github.com/yaml/pyyaml/blob/main/lib/yaml/constructor.py
    r = from_ki_enum(cls, node.value)
    return r
  def the_repr(dumper, data):
    return dumper.represent_scalar(tag, to_ki_enum(data))

  yaml.add_constructor(tag, the_constr)
  yaml.add_representer(cls, the_repr )

  return cls


def yaml_data(cls):
  # Perform operations using the class name
  # print(f"Decorating class: {cls.__name__}")

  # You can add attributes or methods to the class if needed
  # cls.decorated = True

  tag = u"!" + cls.__name__

  def the_constr(loader, node):
    # https://github.com/yaml/pyyaml/blob/main/lib/yaml/constructor.py
    return loader.construct_yaml_object(node, cls)
  def the_repr(dumper, data):
    # https://github.com/yaml/pyyaml/blob/main/lib/yaml/representer.py
    return dumper.represent_yaml_object(tag, data, cls)

  yaml.add_constructor(tag, the_constr)
  yaml.add_representer(cls, the_repr )

  return dataclass(cls)
