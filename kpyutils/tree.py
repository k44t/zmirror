


import os
import natsort



def map_tree(is_branch, list_children, path, handle_leaf = None, handle_branch = None):
  def do_handle_leaf(path, lst):
    r = None
    if handle_leaf is not None:
      r = handle_leaf(path)
    lst.append(r)
    return lst
  def do_handle_branch(path, lst):
    r = None
    if handle_branch is not None:
      r = handle_branch(path)
    lst.append(r)
    return lst

    
  return fold_tree(is_branch, list_children, path, [], do_handle_branch, do_handle_leaf)

def sorted_list_dir(path):
  r = os.listdir(path)
  def concat(child):
    return f"{path}/{child}"
  return map(concat, natsort.natsorted(r))

def map_file_tree(path, handle_leaf = None, handle_branch = None):
  return map_tree(os.path.isdir, sorted_list_dir, path, handle_branch= handle_branch, handle_leaf=handle_leaf)

def fold_file_tree(path, folded, handle_leaf = None, handle_branch = None):
  return fold_tree(os.path.isdir, sorted_list_dir, path, folded, handle_branch= handle_branch, handle_leaf=handle_leaf)

def fold_tree(is_branch, list_children, path, folded, handle_branch = None, handle_leaf = None):
  if is_branch(path):
    if handle_branch is not None:
      folded = handle_branch(path, folded)
    lst = list_children(path)
    for c in lst:
      folded = fold_tree(is_branch, list_children, c, folded, handle_branch, handle_leaf)
    return folded
  elif handle_leaf is not None:
    return handle_leaf(path, folded)