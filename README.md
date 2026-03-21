# zmirror

`zmirror` is a Linux CLI + daemon for managing ZFS mirror backup devices, including LUKS/dm-crypt backed devices.

It listens to `udev` and ZFS events, tracks device/pool state, and can automatically handle operations such as opening encrypted devices, importing pools, onlining/offlining backing devices, and maintenance requests.

Status: beta. Interfaces and behavior can still change.

## Why zmirror

`zmirror` is useful when backup mirrors are not always connected (for example removable disks or off-site/network-backed block devices). It helps keep your main pool performant by allowing backup mirrors to be connected for sync windows and then disconnected again, while still tracking state and maintenance cadence.

## Key Features

- Event-driven daemon (`udev` + ZFS events)
- LUKS/dm-crypt open/close integration
- ZFS pool import/export and backing-device online/offline flows
- Maintenance requests (`scrub`, `trim`, `resilver`) and overdue reporting
- YAML configuration (`example-config.yml` is the reference)
- Persistent cache in SQLite (`/var/lib/zmirror/zmirror-cache.db` by default)

## Security and Safety Notes

- `zmirror` issues storage commands (`zpool`, `zfs`, `cryptsetup`) and should run as `root`.
- Misconfiguration can cause pool import mistakes or data loss. Validate config carefully in a test setup first.
- Keep independent snapshots/backup retention policies outside `zmirror` as well.

## Installation

### Recommended on Debian/Ubuntu (global, root-managed)

For a system service intended to run as `root`, the standard Ubuntu approach is:

1. Install from an `apt` package (official repo/PPA/internal repo)
2. Run daemon as a `systemd` service
3. Execute administrative CLI commands via `sudo`

When published as a Debian/Ubuntu package, installation should look like:

```bash
sudo apt update
sudo apt install zmirror
```

Why this is preferred over `pip install` system-wide:

- integrates with `systemd`, file ownership, and distro policy
- gets safer upgrades/rollbacks
- avoids conflicts with system Python packaging rules (PEP 668)

Build a package from source:

```bash
sudo apt update
sudo apt install build-essential debhelper dh-python python3-all
dpkg-buildpackage -us -uc -b
```

This creates a `.deb` in the parent directory.

### Install from source (developer/local)

```bash
git clone https://github.com/k44t/zmirror.git
cd zmirror
poetry install
```

Run directly from source:

```bash
poetry run python -m zmirror --help
```

## System Integration (manual setup for non-Debian packaging)

If you are not using the Debian package, these integration pieces are still
needed on most distributions and should be installed manually:

- CLI wrappers in your executable path (`zmirror`, `zmirror-trigger`)
- main daemon unit (`zmirror.service`)
- maintenance scheduler (`zmirror-maintenance.service` and `.timer`)
- udev rule (`99-zmirror.rules`) that triggers `zmirror-trigger`
- ZFS ZED hook (`all-zmirror.sh`) to propagate ZFS events into zmirror

Reference files are in the repository under:

- `debian/bin/`
- `debian/zmirror.service`
- `debian/zmirror-maintenance.service`
- `debian/zmirror-maintenance.timer`
- `debian/udev/99-zmirror.rules`
- `debian/zed/all-zmirror.sh`

After manual installation, reload integration points:

```bash
sudo udevadm control --reload-rules
sudo systemctl daemon-reload
sudo systemctl restart zfs-zed
```

Enable runtime units as needed:

```bash
sudo systemctl enable --now zmirror.service
sudo systemctl enable --now zmirror-maintenance.timer
```

## Configuration

- Default config path: `/etc/zmirror/zmirror.yml`
- Start from `example-config.yml` and adapt for your host.

Typical bootstrap:

```bash
sudo install -d /etc/zmirror
sudo cp example-config.yml /etc/zmirror/zmirror.yml
sudoedit /etc/zmirror/zmirror.yml
```

## Running

Start and enable daemon:

```bash
sudo systemctl enable --now zmirror
```

View logs:

```bash
journalctl -u zmirror -f
```

Use CLI (as root or via sudo):

```bash
sudo zmirror list
sudo zmirror status all
sudo zmirror maintenance
```

For full command reference:

```bash
zmirror --help
zmirror list --help
```

## Scheduling

The daemon is event-driven. Periodic maintenance should be scheduled externally (for example with `systemd` timers or `cron`) by invoking commands like `zmirror maintenance`.

The Debian package ships a `zmirror-maintenance.timer` for this purpose.

## Optional boot flow tutorial

`zmirror-local-fs.service` is intentionally not installed by default because it
depends on host-specific boot/storage layout.

See `doc/tutorial-local-fs.md` for an optional setup guide.

## Development

Install dependencies:

```bash
poetry install
```

Run tests:

```bash
poetry run pytest
```

Run a subset:

```bash
poetry run pytest tests/commands/test_commands.py
```

## License

MIT. See `LICENSE`.
