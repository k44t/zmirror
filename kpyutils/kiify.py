
from dataclasses import dataclass
from io import StringIO
from enum import Enum
from datetime import datetime, timedelta
import numbers
from typing import List
import yaml
import inspect



def special_ki_from_json(dct: dict):
  if "_type" in dct:
    if dct["_type"] == "Ki-Symbol":
      return KiSymbol.__from_json__(dct)
    elif dct["_type"] == "Ki-Keyword":
      return KiKeyword.__from_json__(dct)
  return dct



def special_ki_to_json(dt):
  if hasattr(dt, "__to_json__"):
    return dt.__to_json__()
  else:
    return dt

@dataclass
class KiSymbol:
  name: str

  def __kiify__(self, stream):
    stream.print_raw(f"#{self.name}")


  def __to_json__(self):
    return {"_type": "Ki-Symbol", "_name": self.name.lower().replace("_", "-")}
  
  @classmethod
  def __from_json__(cls, json):
    return KiSymbol(json["_name"])


@dataclass
class KiKeyword:
  name: str

  def __kiify__(self, stream):
    stream.print_raw(self.name)

  def __to_json__(self):
    return {"_type": "Ki-Keyword", "_name": self.name.lower().replace("_", "-")}
  
  @classmethod
  def __from_json__(cls, json):
    return KiKeyword(json["_name"])

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
    raise ValueError("not a ki boolean")


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


def escape_ki_string_backslash(result, string, index, delim, backslashes):# pylint: disable=unused-argument
  if string[index] == "\\":
    return escape_ki_string_backslash,  index + 1, backslashes.append("\\")
  else:
    result.append("\\")
    result.append(str(backslashes))
    return escape_ki_string_normal,  index, StringBuilder()


def escape_ki_string_dollar(result, string, index, delim, dollars):# pylint: disable=unused-argument
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


def escape_ki_string_normal(result, string, index, delim, ignoreme):# pylint: disable=unused-argument
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

  def append(self, string):
    self._file_str.write(string)
    return self

  def __str__(self):
    return self._file_str.getvalue()

  def write(self, text):
    self.append(text)

  def print_raw(self, text):
    self.append(text)

  def get_string(self):
    return self._file_str.getvalue()
  
  def flush(self):
    return














#sys.stdout.write("escaped: '")
#sys.stdout.write(escape_ki_string('"', 'hello \\\\\\\\ $$$$ """" World!'))
#sys.stdout.write("'")
#exit()




class KiEnum(Enum):

  def __kiify__(self, ki_stream):
    ki_stream.stream.print_raw("#" + self.name.lower().replace("_", "-"))

  def __to_json__(self):
    return {"_type": "Ki-Enum", "_name": self.name.lower().replace("_", "-")}



class TabbedShiftexStream():
  def __init__(self, stream, indents = 0):
    self.indents = indents
    self.stream = stream

  def indent(self):
    self.indents = self.indents + 1

  def dedent(self):
    self.indents = self.indents - 1


  def newline(self):
    self.print_raw("\n")
    for i in range(0, self.indents):# pylint: disable=unused-variable
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

class KdStream:
  def __init__(self, stream, level = -1):
    if not isinstance(stream, TabbedShiftexStream):
      stream = TabbedShiftexStream(stream)
    self.stream = stream
    self.level = level

  def print_obj(self, obj, nil=KiKeyword("nil")):
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
          self.stream.newline()
        self.stream.print_raw(escape_ki_string('"', line))
        # self.stream.print_raw(line)
      self.stream.print_raw("\"")
    elif isinstance(obj, numbers.Number):
      self.stream.print_raw(str(obj))
    elif isinstance(obj, datetime):
      if obj.microsecond == 0:
        self.stream.print_raw(obj.strftime("%Y-%m-%d'%H:%M:%S"))
      else:
        self.stream.print_raw(obj.strftime("%Y-%m-%d'%H:%M:%S.%f"))
    elif isinstance(obj, timedelta):
      self.print_obj(datetime(1,1,1) + obj)
    elif isinstance(obj, list):
      if len(obj) == 0:
        self.stream.print_raw("[]")
      else:
        self.stream.print_raw("[:")
        self.print_indented_list_content(obj)
    elif isinstance(obj, dict):
      self.stream.print_raw("{:")
      self.stream.indent()
      for i, (key, value) in enumerate(obj.items()):
        self.stream.newline()
        self.print_obj(key)
        self.stream.print_raw(": ")
        self.stream.indent()
        self.print_obj(value)
        self.stream.dedent()
      self.stream.dedent()
    elif obj is None:
      self.print_obj(nil)
    elif hasattr(obj, "__kiify__") and callable(obj.__kiify__):
      obj.__kiify__(self)
    elif inspect.isfunction(obj) or inspect.ismethod(obj):
      self.stream.print_raw("fn ...")
    else:
      self.print_python_obj(obj)

    self.level = self.level + 1


  def print_list_content(self, lst):

    for i, element in enumerate(lst):
      # self.stream.print_raw("||")
      self.stream.newline()
      # self.stream.print_raw(">>")
      self.print_obj(element)
      # self.stream.print_raw("<<")
  def print_indented_list_content(self, lst):

    self.stream.indent()
    self.print_list_content(lst)
    self.stream.dedent()
  
  def print_class_name(self, obj):
    self.stream.print_raw(type(obj).__name__)

  def indent(self):
    self.stream.indent()
  
  def dedent(self):
    self.stream.dedent()

  def print_raw(self, string):
    self.stream.print_raw(string)

  def print_property_prefix(self, prop):
    self.stream.newline()
    # self.stream.print_raw("..>>")
    self.stream.print_raw(prop)
    self.stream.print_raw(": ")

  def print_property_value(self, prop):
    self.stream.print_obj(getattr(self, prop))

  def print_property_and_value(self, prop, val, nil=KiKeyword("nil")):
    self.print_property_prefix(prop)
    self.print_obj(val, nil=nil)


  def print_python_obj(self, obj):
    attrs = dir(obj)
    nattrs = []
    for attr in attrs:
      if not (attr.startswith("_") or callable(getattr(obj, attr))):
        nattrs.append(attr)
    self.print_partial_obj(obj, nattrs)
  
  def print_property(self, obj, prop, hide_if_empty=False, nil=KiKeyword("nil")):
    val = getattr(obj, prop)
    return self.print_property_and_value(prop, val, nil=nil)
  
  def newlines(self, num):
    self.stream.newlines(num)

  def newline(self):
    self.stream.newline()


  def print_partial_obj(self, obj, props: List[str]):
    if self.level == 0:
      self.stream.print_raw("...")
      return
    self.print_class_name(obj)
    self.stream.indent()
    if len(props) > 0:
      for prop in props:
        if hasattr(obj, prop):
          # self.stream.print_raw("..nl>")
          # self.stream.print_raw("..<nl")
          self.print_property(obj, prop)
    else:
      self.stream.print_raw("!")
    self.stream.dedent()

def object_to_kdstring(obj):
  kdstream = KdStream(StringBuilder())
  kdstream.print_obj(obj)
  return kdstream.stream.stream.get_string()


def to_kd_or_none(o):
  if o is None:
    return None
  return to_kd(o)

def to_kd(o, nil=KiKeyword("nil")):
  b = StringBuilder()
  s = KdStream(TabbedShiftexStream(b))
  s.print_obj(o, nil=nil)
  return b.get_string()

def to_ki_enum(data: Enum):
  return "#" + data.name.lower().replace("_", "-")

def from_ki_enum(cls, string: str):
  fixed = string.removeprefix("#").upper().replace("-", "_")
  r = cls[fixed]
  if r is None:
    raise ValueError(f"`{string}` (`{fixed}`) is not an instance of {cls.__class__.__name__}")
  return r



def yaml_enum(cls):
  # Perform operations using the class name
  # print(f"Decorating class: {cls.__name__}")

  # You can add attributes or methods to the class if needed
  # cls.decorated = True

  tag = "!" + cls.__name__

  def the_constr(loader, node):# pylint: disable=unused-argument
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

  tag = "!" + cls.__name__

  def the_constr(loader, node):
    # https://github.com/yaml/pyyaml/blob/main/lib/yaml/constructor.py  
    values = loader.construct_mapping(node)
    # import inspect
    # print(inspect.signature(cls.__init__).parameters)
    return cls(**values)
    # return loader.construct_yaml_object(node, cls)
  def the_repr(dumper, data):
    # https://github.com/yaml/pyyaml/blob/main/lib/yaml/representer.py
    return dumper.represent_yaml_object(tag, data, cls)

  yaml.add_constructor(tag, the_constr)
  yaml.add_representer(cls, the_repr )

  return dataclass(cls)



def yes_no_absent_or_dict(e, prop, on_absent, raised_error=None):
  if prop not in e:
    return on_absent
  if e[prop] == "yes":
    return True
  if e[prop] == "no":
    return False
  if isinstance(e[prop], bool):
    return e[prop]
  if raised_error:
    raise ValueError(f"{raised_error}: {prop} must either be `yes` or `no` (or alltogether absent for `no`)")



def is_yes(v):
  if v == "yes":
    return True
  elif v == True:
    return True



def is_yes_or_true(v):
  if v == "yes":
    return True
  if v == "true":
    return True
  elif v == True:
    return True
  
def to_yes(v):
  if is_yes_or_true(v):
    return "yes"
  else:
    return "no"



def date_or_datetime(value):
  for fmt in ('%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d\'%H:%M:%S'):
    try:
      return datetime.strptime(value, fmt)
    except ValueError:
      continue
  raise ValueError(f"Not a valid date or datetime: '{value}'.")



def to_kd_date(value):
  if isinstance(value, datetime) or isinstance(value, timedelta):
    return to_kd(value)
  else:
    return value