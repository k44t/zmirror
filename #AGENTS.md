Deployed zmirror config is not the repo `example-config.yml`.

For runtime debugging on this host, check the stow package under:

- `/#/system/zmirror/etc/zmirror/zmirror.yml`

Current confirmed live issue source:

- `zvol|pool:big|name:theo` has `on_children_offline: - offline`
- the same pattern also exists for other live zvols such as `theo-data`, `blubak`, and `zmirror-blubak-gamma/blubak`

When investigating production logs, prefer the deployed config over repo examples.
