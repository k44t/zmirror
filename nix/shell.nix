{ pkgs ? import <nixpkgs> {} }: let

  kpyutils = pkgs.python3Packages.callPackage ../../kpyutils/nix/python-package.nix {};

in pkgs.mkShell {
  packages = [
    (pkgs.python3.withPackages (ps: with ps; [
      natsort
      pyyaml
      dateparser
      pkgs.python3Packages.systemd
      kpyutils
    ]))
  ];
}