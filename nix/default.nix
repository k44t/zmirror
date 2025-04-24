{pkgs, ...}: let

zmirror = pkgs.writeShellScriptBin "zmirror" ''
  #!/usr/bin/env bash
  export PATH=${pkgs.callPackage ./python.nix {}}/bin:${pkgs.zfs}/bin
  
  python /#/zion/zmirror/src/zmirror.py "$@"
'';


# for debugging would be:
# python -Xfrozen_modules=off -m debugpy --wait-for-client --listen localhost:8888 /#/zion/zmirror/zmirror_trigger.py "$@"

zmirror-trigger = "${pkgs.callPackage ./python.nix {}}/bin/python /#/zion/zmirror/src/zmirror_trigger.py";

in {


  services.udev.extraRules = ''
    SUBSYSTEM=="block", RUN+="${zmirror-trigger}"
    
    SUBSYSTEM=="block", ACTION=="add|change", PROGRAM="${ pkgs.writeScriptBin "extract-raid-name" (''#!${pkgs.bash}/bin/bash
    '' + builtins.readFile ./scripts/extract-raid-name.sh) }/bin/extract-raid-name", ENV{ZMIRROR_MD_NAME}="%c", SYMLINK+="mapper/%c"

    SUBSYSTEM=="block", ACTION=="add|change", PROGRAM="${ pkgs.writeScriptBin "extract-raid-part-name" (''#!${pkgs.bash}/bin/bash
    '' + builtins.readFile ./scripts/extract-raid-part-name.sh) }/bin/extract-raid-part-name", SYMLINK+="mapper/%c"
  '';

  # KERNEL=="md*", SUBSYSTEM=="block", ACTION=="add|change", ENV{UDISKS_MD_NAME}=="*", PROGRAM="${ pkgs.writeScriptBin "extract-raid-name" (builtins.readFile ./src-bash/extract-raid-name.sh) }/bin/extract-raid-name %E{UDISKS_MD_NAME}", SYMLINK+="mapper/%c"

  environment.systemPackages = [ zmirror ];

  environment.etc = {
    "zfs/zed.d/all-zmirror.sh" = {
      mode = "0544";
      text = ''#!${pkgs.bash}/bin/bash
        [ -f "''${ZED_ZEDLET_DIR}/zed.rc" ] && . "''${ZED_ZEDLET_DIR}/zed.rc"
          . "''${ZED_ZEDLET_DIR}/zed-functions.sh"
                
	      zed_log_msg zmirror running

        ${zmirror-trigger}
      '';
    };
  };

}