

def is_yes(arg):
  return arg == "yes"

def confirm(question, check=is_yes):
  response = input(question).strip().lower()
  return check(response)