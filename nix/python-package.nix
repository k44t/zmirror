{ lib, buildPythonPackage, python3Packages, rsync, python3, poetry-core, zfs, tree }:
let

package = buildPythonPackage rec {
  pname = "zmirror-core";
  version = "0.1.2";

  # this needs to be done so nix really copies all source files into the nix store (instead of symlinking)
  src = builtins.path { path = ./..; };

  propagatedBuildInputs = with python3Packages; [
    natsort
    pyyaml
    dateparser
    python3Packages.systemd
    kpyutils
  ];
  
  nativeBuildInputs = [ 
    tree
    rsync 
    poetry-core
  ];

  format = "pyproject";

  
  unpackPhase = ''
    rsync -av --exclude='.venv' --exclude='.vscode' --no-perms --no-group --no-owner ${src}/ ./
  '';


  postInstall = ''
    # the pythonOutputDistHook will fail if this directory does not exist
    # even though whatever happened before already put all files in their proper paces
    mkdir -p $out/dist
  '';

  meta = with lib; {
    description = "Your project description";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
  };
};


in package