{ lib, stdenv, zfs, python3Packages, writeShellScript, python3 }:
let


py = python3.withPackages (ptpkgs: [zmirror-core ptpkgs.pyyaml]);

script = writeShellScript "zmirror" ''
  PATH=${zfs}/bin:$PATH ${py}/bin/python -m zmirror "$@"
'';
trigger-script = writeShellScript "zmirror-trigger" ''
  ${py}/bin/python -m zmirror.trigger "$@"
'';

# python -Xfrozen_modules=off -m debugpy --wait-for-client --listen localhost:8888 /#/projects/zmirror/src/zmirror.py "$@"

zmirror-core = python3Packages.callPackage ./python-package.nix {};


package = stdenv.mkDerivation rec {
  pname = "zmirror";
  version = "0.1.0";

  # this needs to be done so nix really copies all source files into the nix store (instead of symlinking)
  src = builtins.path { path = ./..; };
  

  postInstall = ''

    mkdir -p $out/bin
    cp ${script} $out/bin/zmirror
    cp ${trigger-script} $out/bin/zmirror-trigger
    chmod a+x $out/bin/*

    mkdir -p $out/lib/udev/rules.d
    cp ./udev/99-zmirror.rules $out/lib/udev/rules.d
    sed -i "s|/usr/local/bin/|$out/bin/|g" $out/lib/udev/rules.d/99-zmirror.rules

  '';

  propagatedBuildInputs = [
    zmirror-core
  ];

  meta = with lib; {
    description = "zmirror zfs backup sync service";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
  };
};


in package