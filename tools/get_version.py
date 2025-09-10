def get_version():
  with open("VERSION") as f:
    return f.read().strip()