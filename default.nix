{pkgs, ...}: let

zmirror = pkgs.writeShellScriptBin "zmirror" ''
  #!/usr/bin/env bash
  export PATH=${pkgs.callPackage ./python.nix {}}/bin:${pkgs.zfs}/bin
  
  python /#/zion/zmirror/zmirror.py "$@"
'';


# for debugging would be:
# python -Xfrozen_modules=off -m debugpy --wait-for-client --listen localhost:8888 /#/zion/zmirror/zmirror_trigger.py "$@"

zmirror-trigger = pkgs.writeShellScript "zmirror-trigger" ''
  #!/usr/bin/env bash
  ${pkgs.callPackage ./python.nix {}}/bin/python /#/zion/zmirror/zmirror_trigger.py
'';

in {

  systemd.timers."zmirror-scrub" = {
    enable = true;
    description = "runs zmirror at night";
    wantedBy = [ "timers.target" ];         
    timerConfig = {                         
      OnCalendar = "03:00";                
      Persistent = true;             
    };                                      
  };

  systemd.services = { 
    "zmirror-scrub" = {
      enable = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${zmirror} scrub";
      };
    };

    "zmirror-socket" = {
      enable = false;
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${zmirror} daemon";
      };
    };
  };

  services.udev.extraRules = ''
    SUBSYSTEM=="block", RUN+="${zmirror-trigger}"
  '';

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