/*{ python3
, stdenv
, callPackage
 }:
let

  python = callPackage ./python.nix {};

in

stdenv.mkDerivation rec {
  name = "zmirror";
  propagatedBuildInputs = [
    python
  ];
  dontUnpack = true;
  installPhase = "install -Dm755 ${./zmirror.py} $out/bin/$name";
}*/

{
  writeShellScriptBin
, callPackage
, zfs}: 


writeShellScriptBin "zmirror" ''
  #!/usr/bin/env bash
  export PATH=${callPackage ./python.nix {}}/bin:${zfs}/bin
  python /#/zion/zmirror/src/zmirror.py "$@"
  # python -Xfrozen_modules=off -m debugpy --wait-for-client --listen localhost:8888 /#/zion/zmirror/src/zmirror.py "$@"
''

