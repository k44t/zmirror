# Optional Boot Integration: local-fs group

`zmirror-local-fs.service` is intentionally not installed by default.

This flow is host-specific and only makes sense if your boot sequence needs
`zmirror` to online a specific entity group during startup (for example pools
or devices grouped under `local-fs` in your `zmirror.yml`).

## When to use it

Use this only if all of the following are true:

- your config defines a group intended for boot-time onlining (for example `local-fs`)
- those entities are expected to be available early in boot
- your system boot order is validated for this dependency

If this does not apply to your host, skip this tutorial.

## Unit example

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

## Validation checklist

- `systemctl status zmirror.service`
- `systemctl status zmirror-local-fs.service`
- `journalctl -u zmirror -b`
- confirm `local-fs` group names match your `/etc/zmirror/zmirror.yml`
