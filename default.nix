{ python3
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
}