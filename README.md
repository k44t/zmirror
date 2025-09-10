# zmirror

This project is in the beta phase. Bugs might exist, changes to API and CLI might happen frequently, documentation might not be up to date.

## Description

`zmirror` is a linux system service that enables you to use ZFS encrypted mirror devices as backups.

### How it works

`zmirror` listens to `udev` and `ZED` events to online or offline devices and zpools based on configuration.

`zmirror`'s YAML configuration file gives you fine-grained control over how zmirror should treat each disk, zpool and zdev. 

All configuration features are documented inside `example-config.yml` which incidentally
is the active configuration of the devvythelopper of `zmirror` (sic).



### Risk Mitigation

`zmirror`'s backup strategy mitigates the following risks:

- internal (or always connected external) disk failure
- failure of server and all connected disks (e.g. caused by a power surge)
- EMP (and radiation-caused bitrot) 
  - as long as the backup disks are stored in an EMP safe enclosure
- bitrot
  - as long as the backup disks are connected often enough
- local catastrophe
  - as long as the backup disks are stored in multiple physical locations

`zmirror`'s backup strategy **CANNOT** mitigate the following risks:

- bugs in ZFS that make me lose some or all of the data inside the backups
- hackers that maliciously delete data WHILE a backup disk is connected

To mitigate these types of risks one would need permanent backups (i.e. millenium disks or tape backups).



### Features

The following features are implemented:

- opening/closing LUKS encrypted partitions (in which the zpools reside)
- importing/exporting `zpool`s
- onlining/offlining the `zpool`s backing devices (`zdev`)
- maintenance schedules for `scrub`, `resilver` and `trim`
- reporting maintenance status
- event handlers
- force-enabling TRIM (sometimes the kernel fails to recognize TRIM capabilities 
  over USB)
- manual commands


### Scheduling

`zmirror daemon` itself does not have an inbuilt scheduler. Instead it relies
on systemd or or cron to run `zmirror maintenance` at some user-specified 
time of day (or week or whatever).


## Installation

Unless there is an official package for your linux distribution clone the project:

```bash
git clone https://github.com/k44t/zmirror.git
cd zmirror
```

On nixOS you can change `/etc/nix/configuration.nix`:

```nix
  imports = [
    /path/to/zmirror/nix/nixos.nix
  ];

  services.zmirror = {
    enable = true;
    maintenance-schedule = "03:00";
    # config-file = "${./zmirror.yml}";
    config-path = "${/path/to/config/file/zmirror.yml}";
  };
```

On other distributions (untested by the devvythelopper) build the project (after installing poetry):

```bash
poetry build
```

Install system-wide:

```
sudo pip3 install dist/zmirror-*.whl
```

Install systemd bindings for python so that zmirror can write its log messages to the system log.

On ubuntu you can do

```bash
apt install python3-systemd
```

At this point you might want to open a window to follow the logs:

```
journalctl -f
```

On a debian-like distribution, you can simply install udev rules (`/etc/udev/rules.d/99-zmirror.rules`), ZED script (`/etc/zfs/zed.d/all-zmirror.sh`) and the `/usr/sbin/zmirror` and `/usr/sbin/zmirror-trigger` scripts by copying them:

```
sudo rsync -av ./debian/ /
```

Be sure to 

On other distributions locations and script contents (paths) might need adapting.

Reload udev rules:

```
sudo udevadm control --reload-rules
```

Restart the ZFS event daemon (ZED)

```
sudo systemctl restart zfs-zed
```

Properly configure `zmirror` at this point. You may copy `example-config.yml` to `/etc/zmirror/zmirror.yml` and adapt carefully.

Most instances of malconfiguration should simply result in error messages or just simply not the results you desire.

Dataloss can occur for example if `zmirror` imports a pool when only a device is present that does not have the newest data. This might also be the result of not configuring a "leader" mirror device (the one with the newest data) properly (for example the wrong path to the key-file) while configuring "follower" mirror device properly, so that zmirror imports the pool with only the "follower" device and later imports the "leader" device once configuration has been corrected.

Misconfiguration of zpools (outside of zmirror) might result in system instability. This might be the result of a zpool that is usually imported with a different root path `-R /some/path`, and `zmirror` which knows nothing of changing pool root on import imports it under `/`.

The developers are not responsible for any damages caused by using `zmirror`. Use at your own risk as agreed per the LICENSE.

Start `zmirror`:

```
sudo systemctl start zmirror
```

Alternatively you can also run zmirror from the project directory. First prepare:

```bash
# create venv
poetry install

# activate venv
source ./.venv/bin/activate
```

As the user under which you want to run zmirror (must be `root` if you want zmirror to not just report things but also do its job):

```
# start zmirror daemon
python -m zmirror daemon
```

If it starts successfully, you can then run commands as the same user (or as `root`):

```
zmirror list
```

see 

```
zmirror --help
```

For all the things you can tell the `zmirror daemon` to do for you.



## License

The code is fully MIT licensed. See the LICENSE file.
