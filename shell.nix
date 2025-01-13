{ pkgs ? import <nixpkgs> {} , ... }:let
  
in

pkgs.mkShell {
  
  
  NIX_CONFIG = ''
    # this enables flakes for all nix-commands run inside this shell
    # experimental-features = nix-command flakes
  '';
  
  shellHook = ''
  '';
  
  
  buildInputs = with pkgs; [ 
    (pkgs.callPackage ./. {}) 
  ];
}