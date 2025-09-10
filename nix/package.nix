{ lib, stdenv, zfs, python3Packages, python3, writeShellScript }:
let


py = python3.withPackages (pypkgs: [
  (pypkgs.callPackage ./python-package.nix {})
]);


script = writeShellScript "zmirror" ''
  PATH=${zfs}/bin:$PATH ${py}/bin/python -m zmirror "$@"
'';
trigger-script = writeShellScript "zmirror-trigger" ''
  ${py}/bin/python -m zmirror.trigger "$@"
'';

# python -Xfrozen_modules=off -m debugpy --wait-for-client --listen localhost:8888 /#/projects/zmirror/src/zmirror.py "$@"

package = stdenv.mkDerivation rec {
  pname = "zmirror";
  version = import ./version.nix;

  # this needs to be done so nix really copies all source files into the nix store (instead of symlinking)
  src = builtins.path { path = ./..; };
  

  postInstall = ''

    mkdir -p $out/bin
    cp ${script} $out/bin/zmirror
    cp ${trigger-script} $out/bin/zmirror-trigger
    chmod a+x $out/bin/*

    mkdir -p $out/lib/udev/rules.d
    cp ./debian/etc/udev/rules.d/99-zmirror.rules $out/lib/udev/rules.d
    sed -i "s|/usr/local/bin/|$out/bin/|g" $out/lib/udev/rules.d/99-zmirror.rules

  '';

  propagatedBuildInputs = [
  ];

  meta = with lib; {
    description = "ZFS-based backup service";
    license = licenses.mit;
    maintainers = with maintainers; [ ];
  };
};


in package