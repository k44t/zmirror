{ lib, rsync, poetry-core, zfs, tree, python, buildPythonPackage }:


buildPythonPackage rec {
  pname = "zmirror-core";
  version = import ./version.nix;

  disabled = python.pythonOlder "3.7";

  # this needs to be done so nix really copies all source files into the nix store (instead of symlinking)
  src = builtins.path { path = ./..; };

  propagatedBuildInputs = with python.pkgs; [
    natsort
    pyyaml
    dateparser
    systemd
    kpyutils
  ];
  
  nativeBuildInputs = [ 
    tree
    rsync 
    poetry-core
  ];

  format = "pyproject";

  
  unpackPhase = ''
    rsync -av --exclude='.venv' --exclude='.vscode' --exclude='.notifier' --no-perms --no-group --no-owner ${src}/ ./
  '';


  postInstall = ''
    # the pythonOutputDistHook will fail if this directory does not exist
    # even though whatever happened before already put all files in their proper paces
    mkdir -p $out/dist
  '';

  meta = with lib; {
    description = "ZFS Based Backup Solution";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
  };
}

