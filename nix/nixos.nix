{config, pkgs, lib, ...}: let

  cfg = config.services.zmirror;

in with lib; with types; {
  imports = [
    ./nixpkgs.nix
  ];

    
  options = {
    services.zmirror = mkOption {
      type = (submodule {
        options = {
          enable = mkEnableOption "zmirror";
          config-file = mkOption {
            type = nullOr path;
            default = null;
            description = "The configuration file (a nix path). Must be null if `config-path` is set.";
          };
          config-path = mkOption {
            type = nullOr str;
            default = null;
            description = "A filepath (string) to the configuration file. Useful for testing without rebuilding nixos on every configuration change. Must be null if `config-file` is set.";
          };
          maintenance-schedule = mkOption {
            type = nullOr str;
            default = "03:00";
          };
        };
      });
      default = {};
    };
  };

  config = lib.mkIf (cfg.enable) {

    services.udev.packages = [ pkgs.zmirror ];

    environment.systemPackages = [ pkgs.zmirror ];

    environment.etc = {
      "zfs/zed.d/all-zmirror.sh" = {
        mode = "0555";
        text = ''
          #!${pkgs.bash}/bin/sh
          [ -f "''${ZED_ZEDLET_DIR}/zed.rc" ] && . "''${ZED_ZEDLET_DIR}/zed.rc"
            . "''${ZED_ZEDLET_DIR}/zed-functions.sh"

          zed_log_msg "zmirror-trigger: sending event to zmirror daemon"
          ${pkgs.zmirror}/bin/zmirror-trigger
        '';
      };
      "zmirror/zmirror.yml" = lib.mkIf (cfg.config-file != null) {
        mode = "0444";
        source = cfg.config-file;
      };
    };


    systemd = {
      timers = lib.mkIf (cfg.maintenance-schedule != null) {
        "zmirror-maintenance" = {
          wantedBy = [ "timers.target" ];
          timerConfig.OnCalendar = "daily";
          timerConfig.Persistent = true;
        };
      };
      services = {
        "zmirror" = {
          script = "zmirror daemon ${optionalString (cfg.config-path != null) "--config-path '${cfg.config-path}'"}";
          path = with pkgs; [zfs zmirror];
          wantedBy = ["local-fs.target"];
          reloadTriggers = [cfg.config-file cfg.config-path];
          reload = "zmirror reload-config";
        };
        "zmirror-maintenance" = lib.mkIf (cfg.maintenance-schedule != null) {
          script = "zmirror maintenance";
          path = with pkgs; [zmirror];
        };
      };
    };

  };
}