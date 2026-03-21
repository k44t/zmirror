# zmirror tutorial

This tutorial collects the longer background and operations guidance that used
to live in the README, plus optional host-specific boot integration.

## Scenario: Friends

Say you are friends with a family who also runs a homeserver with ZFS. You
might agree that they provide storage for an off-site backup for you, while in
turn you provide storage for their offsite backup.

You could use another replication tool for this purpose, but that can require
granting access to datasets and metadata. If you care about privacy, one setup
is to use a remote block device and then apply your own LUKS encryption and ZFS
mirror strategy on top.

Example flow:

1. Friends provide a ZFS volume (block device) and private network connectivity.
2. You connect via VPN and map the remote block device.
3. You format it with LUKS2 and use it as a mirror backing device.
4. `zmirror` onlines/offlines backup mirrors based on events and policy.

This keeps local performance high (because remote mirror devices do not stay
connected all the time) while still performing periodic fully encrypted syncs.

## How it works

For every internal zpool for which you want a backup, you mirror its devices on
one or more external devices (`zpool attach`).

When backup devices are connected, `zmirror` tracks state and drives operations
like import, online/offline, and maintenance according to configuration.

`zmirror` listens to:

- `udev` block-device events
- ZFS ZED events

And can handle nested setups, for example zpools whose backing devices are
inside encrypted containers and/or zvols.

All configuration features are documented in `example-config.yml`.

## Risk mitigation

This strategy helps mitigate:

- internal disk failure
- failure of host plus connected disks (for example surge), if backups are disconnected
- local catastrophe, if backups are stored across locations
- some bitrot exposure, if backups are connected often enough for scrub/update cadence

This strategy does not eliminate:

- software bugs in storage stack
- malicious deletion while backup media is connected

For stronger guarantees, combine `zmirror` workflows with immutable/offline
snapshots and additional long-term backup media.

## Safety notes

Misconfiguration can lead to data loss or wrong import behavior. Validate in a
test setup first.

Two common failure modes:

- importing a pool with an outdated device before the newest mirror member is available
- importing with wrong assumptions about pool root/mount behavior

Always review your `required` mirror members, key-file paths, and import/mount
expectations.

## Manual integration (non-Debian packaging)

If you are not using the Debian package, most distributions still need these
integration components installed manually:

- executable wrappers (`zmirror`, `zmirror-trigger`)
- daemon unit (`zmirror.service`)
- maintenance scheduler (`zmirror-maintenance.service` and `.timer`)
- udev rule (`99-zmirror.rules`)
- ZED hook (`all-zmirror.sh`)

Repository reference files:

- `debian/bin/`
- `debian/zmirror.service`
- `debian/zmirror-maintenance.service`
- `debian/zmirror-maintenance.timer`
- `debian/udev/99-zmirror.rules`
- `debian/zed/all-zmirror.sh`

After installation:

```bash
sudo udevadm control --reload-rules
sudo systemctl daemon-reload
sudo systemctl restart zfs-zed
sudo systemctl enable --now zmirror.service
sudo systemctl enable --now zmirror-maintenance.timer
```

## Optional boot integration: local-fs group

`zmirror-local-fs.service` is intentionally not installed by default.

This flow is host-specific and only makes sense if your boot sequence needs
`zmirror` to online a specific entity group during startup (for example pools
or devices grouped under `local-fs` in `zmirror.yml`).

Create `/etc/systemd/system/zmirror-local-fs.service`:

```ini
[Unit]
Description=zmirror unit for loading startup local-fs entities
Wants=zmirror.service
After=zmirror.service

StartLimitBurst=5
StartLimitIntervalSec=300

[Service]
Type=oneshot
ExecStart=/usr/bin/zmirror online group local-fs
Restart=on-failure
RestartSec=5

[Install]
WantedBy=remote-fs.target
```

Then enable it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now zmirror-local-fs.service
```

Validate:

- `systemctl status zmirror.service`
- `systemctl status zmirror-local-fs.service`
- `journalctl -u zmirror -b`
- verify `local-fs` group names match `/etc/zmirror/zmirror.yml`
