{pkgs, ...}: {
  nixpkgs.overlays = [
    (final: prev: {
      zmirror = prev.callPackage ./package.nix {};
    })
  ];

}
