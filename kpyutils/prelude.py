import sys


def msg(str):
  sys.stderr.write(str)
  sys.stderr.write('\n')


def msgProp(prop, val):
  sys.stderr.write(prop)
  sys.stderr.write(": ")
  sys.stderr.write(val)

