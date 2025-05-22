{pkgs, ...}: let

in {
  imports = [
    ./nixpkgs.nix
  ];

  services.udev.packages = [ pkgs.zmirror ];

  /*
    
    SUBSYSTEM=="block", ACTION=="add|change", PROGRAM="${ pkgs.writeScriptBin "extract-raid-name" (''#!${pkgs.bash}/bin/bash
    '' + builtins.readFile ./scripts/extract-raid-name.sh) }/bin/extract-raid-name", ENV{ZMIRROR_MD_NAME}="%c", SYMLINK+="mapper/%c"

    SUBSYSTEM=="block", ACTION=="add|change", PROGRAM="${ pkgs.writeScriptBin "extract-raid-part-name" (''#!${pkgs.bash}/bin/bash
    '' + builtins.readFile ./scripts/extract-raid-part-name.sh) }/bin/extract-raid-part-name", SYMLINK+="mapper/%c"
  '';
  */


  environment.systemPackages = [ pkgs.zmirror ];

  environment.etc = {
    "zfs/zed.d/all-zmirror.sh" = {
      mode = "0544";
      text = ''#!${pkgs.bash}/bin/bash
        ${pkgs.zmirror}/bin/zmirror-trigger
      '';
    };
  };

  /*

        [ -f "''${ZED_ZEDLET_DIR}/zed.rc" ] && . "''${ZED_ZEDLET_DIR}/zed.rc"
          . "''${ZED_ZEDLET_DIR}/zed-functions.sh"
                
	      zed_log_msg zmirror running

  */

}