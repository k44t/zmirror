---
date: 2025-09-10
section: 1
title: ZMIRROR
---

# NAME

zmirror

# SYNOPSIS

**zmirror** \[-h\] \[\--version\]
{daemon,clear-cache,reload-config,scrub-all,scrub-overdue,resilver-overdue,trim-all,trim-overdue,online-all,status-all,daemon-version,maintenance,online,offline,status,trim,scrub,list,enable,disable,set,get}
\...

# POSITIONAL ARGUMENTS

**zmirror** *daemon*

:   starts zmirror in daemon mode

**zmirror** *clear-cache*

:   clears the cache and removes the cache file (which stores the dates
    of when the maintenance tasks were last run). Triggers a
    configuration reload.

**zmirror** *reload-config*

:   reloads the configuration.

**zmirror** *scrub-all*

:   requests all configured zdevs to be scrubbed. This will bring all
    necessary and available parent devices (i.e. dm-crypts) online.

**zmirror** *scrub-overdue*

:   requests zdevs to be scrubbed if they are behind their configured
    \`scrub_interval\`. This will bring all necessary and available
    parent devices (i.e. \`dm-crypt\`s) online.

**zmirror** *resilver-overdue*

:   requests zdevs to be resilvered if they are behind their configured
    \`resilver_interval\`. Since a resilver happens whenever a mirrored
    device is brought online, this really does nothing but (try to)
    online the respective devices.

**zmirror** *trim-all*

:   requests all configured zdevs to be trimmed. This will bring all
    necessary and available parent devices (i.e. \`dm-crypt\`s) online.

**zmirror** *trim-overdue*

:   requests zdevs to be trimmed if they are behind their configured
    trim_interval. This will bring all necessary and available parent
    devices (i.e. \`dm-crypt\`s) online.

**zmirror** *online-all*

:   requests all configured devices to be onlined.

**zmirror** *status-all*

:   shows the status of all configured devices

**zmirror** *daemon-version*

:   shows the version of the (currently running) zmirror daemon

**zmirror** *maintenance*

:   triggers all maintenance tasks (scrub and trim as scheduled as well
    as onlining devices that should be brought up to date
    \[resilvered\]). This is what you want to schedule via a cronjob or
    a systemd timer. It makes sense to do this at night on a weekday
    where there is not much load on your machine. This will online all
    devices that are present and need maintenance. The devices will only
    be taken offline afterwards if you have configured the respective
    event timers to take them offline (i.e. \`on_resilvered\` set to
    \`offline\`).

**zmirror** *online*

:   request device to go online

**zmirror** *offline*

:   request device to go offline

**zmirror** *status*

:   show device status

**zmirror** *trim*

:   request device trim

**zmirror** *scrub*

:   request device to be scrubbed

**zmirror** *list*

:   list devices fulfilling conditions

**zmirror** *enable*

:   enable zmirror daemon property

**zmirror** *disable*

:   disable zmirror daemon property

**zmirror** *set*

:   set zmirror daemon property to value

**zmirror** *get*

:   get zmirror daemon property value

# COMMAND *\'zmirror* daemon\'

usage: zmirror daemon \[-h\] \[\--config-path CONFIG_PATH\]
\[\--cache-path CACHE_PATH\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* daemon\'

**\--config-path** *CONFIG_PATH*

:   the path to the config file. May be set via the environment variable
    \`ZMIRROR_CONFIG_PATH\`. Defaults to
    \`/etc/zmirror/zmirror-config.yml\`

<!-- -->

**\--cache-path** *CACHE_PATH*

:   the path to the cache file in which zmirror stores device state. May
    be set via the environment variable \`ZMIRROR_CACHE_PATH\`. Defaults
    to \`/var/lib/zmirror/zmirror-cache.yml\`

<!-- -->

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* clear-cache\'

usage: zmirror clear-cache \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* clear-cache\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* reload-config\'

usage: zmirror reload-config \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* reload-config\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* scrub-all\'

usage: zmirror scrub-all \[-h\] \[\--socket-path SOCKET_PATH\]
\[\--cancel\]

# OPTIONS *\'zmirror* scrub-all\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

<!-- -->

**\--cancel**

:   # COMMAND *\'zmirror* scrub-overdue\'

usage: zmirror scrub-overdue \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* scrub-overdue\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* resilver-overdue\'

usage: zmirror resilver-overdue \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* resilver-overdue\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* trim-all\'

usage: zmirror trim-all \[-h\] \[\--socket-path SOCKET_PATH\]
\[\--cancel\]

# OPTIONS *\'zmirror* trim-all\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

<!-- -->

**\--cancel**

:   # COMMAND *\'zmirror* trim-overdue\'

usage: zmirror trim-overdue \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* trim-overdue\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* online-all\'

usage: zmirror online-all \[-h\] \[\--socket-path SOCKET_PATH\]
\[\--cancel\]

# OPTIONS *\'zmirror* online-all\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

<!-- -->

**\--cancel**

:   # COMMAND *\'zmirror* status-all\'

usage: zmirror status-all \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* status-all\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* daemon-version\'

usage: zmirror daemon-version \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* daemon-version\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* maintenance\'

usage: zmirror maintenance \[-h\] \[\--socket-path SOCKET_PATH\]

# OPTIONS *\'zmirror* maintenance\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* online\'

usage: zmirror online \[-h\] \[\--socket-path SOCKET_PATH\]
\[\--cancel\] {disk,partition,zpool,zfs-volume,dm-crypt,zdev} \...

# POSITIONAL ARGUMENTS *\'zmirror online\'*

# COMMAND *\'zmirror* online disk\'

usage: zmirror online disk \[-h\] \[\--cancel\] uuid

**uuid**

:   id field

# OPTIONS *\'zmirror* online disk\'

**\--cancel**

:   # COMMAND *\'zmirror* online partition\'

usage: zmirror online partition \[-h\] \[\--cancel\] name

**name**

:   id field

# OPTIONS *\'zmirror* online partition\'

**\--cancel**

:   # COMMAND *\'zmirror* online zpool\'

usage: zmirror online zpool \[-h\] \[\--cancel\] name

**name**

:   id field

# OPTIONS *\'zmirror* online zpool\'

**\--cancel**

:   # COMMAND *\'zmirror* online zfs-volume\'

usage: zmirror online zfs-volume \[-h\] \[\--cancel\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* online zfs-volume\'

**\--cancel**

:   # COMMAND *\'zmirror* online dm-crypt\'

usage: zmirror online dm-crypt \[-h\] \[\--cancel\] name

**name**

:   id field

# OPTIONS *\'zmirror* online dm-crypt\'

**\--cancel**

:   # COMMAND *\'zmirror* online zdev\'

usage: zmirror online zdev \[-h\] \[\--cancel\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* online zdev\'

**\--cancel**

:   # OPTIONS *\'zmirror* online\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

<!-- -->

**\--cancel**

:   # COMMAND *\'zmirror* offline\'

usage: zmirror offline \[-h\] \[\--socket-path SOCKET_PATH\]
{disk,partition,zpool,zfs-volume,dm-crypt,zdev} \...

# POSITIONAL ARGUMENTS *\'zmirror offline\'*

# COMMAND *\'zmirror* offline disk\'

usage: zmirror offline disk \[-h\] \[\--cancel\] uuid

**uuid**

:   id field

# OPTIONS *\'zmirror* offline disk\'

**\--cancel**

:   # COMMAND *\'zmirror* offline partition\'

usage: zmirror offline partition \[-h\] \[\--cancel\] name

**name**

:   id field

# OPTIONS *\'zmirror* offline partition\'

**\--cancel**

:   # COMMAND *\'zmirror* offline zpool\'

usage: zmirror offline zpool \[-h\] \[\--cancel\] name

**name**

:   id field

# OPTIONS *\'zmirror* offline zpool\'

**\--cancel**

:   # COMMAND *\'zmirror* offline zfs-volume\'

usage: zmirror offline zfs-volume \[-h\] \[\--cancel\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* offline zfs-volume\'

**\--cancel**

:   # COMMAND *\'zmirror* offline dm-crypt\'

usage: zmirror offline dm-crypt \[-h\] \[\--cancel\] name

**name**

:   id field

# OPTIONS *\'zmirror* offline dm-crypt\'

**\--cancel**

:   # COMMAND *\'zmirror* offline zdev\'

usage: zmirror offline zdev \[-h\] \[\--cancel\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* offline zdev\'

**\--cancel**

:   # OPTIONS *\'zmirror* offline\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* status\'

usage: zmirror status \[-h\] \[\--socket-path SOCKET_PATH\]
{disk,partition,zpool,zfs-volume,dm-crypt,zdev} \...

# POSITIONAL ARGUMENTS *\'zmirror status\'*

# COMMAND *\'zmirror* status disk\'

usage: zmirror status disk \[-h\] uuid

**uuid**

:   id field

# COMMAND *\'zmirror* status partition\'

usage: zmirror status partition \[-h\] name

**name**

:   id field

# COMMAND *\'zmirror* status zpool\'

usage: zmirror status zpool \[-h\] name

**name**

:   id field

# COMMAND *\'zmirror* status zfs-volume\'

usage: zmirror status zfs-volume \[-h\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# COMMAND *\'zmirror* status dm-crypt\'

usage: zmirror status dm-crypt \[-h\] name

**name**

:   id field

# COMMAND *\'zmirror* status zdev\'

usage: zmirror status zdev \[-h\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* status\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* trim\'

usage: zmirror trim \[-h\] \[\--socket-path SOCKET_PATH\] {zdev} \...

# POSITIONAL ARGUMENTS *\'zmirror trim\'*

# COMMAND *\'zmirror* trim zdev\'

usage: zmirror trim zdev \[-h\] \[\--cancel\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* trim zdev\'

**\--cancel**

:   # OPTIONS *\'zmirror* trim\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* scrub\'

usage: zmirror scrub \[-h\] \[\--socket-path SOCKET_PATH\] \[\--cancel\]
{zpool,zdev} \...

# POSITIONAL ARGUMENTS *\'zmirror scrub\'*

# COMMAND *\'zmirror* scrub zpool\'

usage: zmirror scrub zpool \[-h\] name

**name**

:   id field

# COMMAND *\'zmirror* scrub zdev\'

usage: zmirror scrub zdev \[-h\] pool name

**pool**

:   id field

<!-- -->

**name**

:   id field

# OPTIONS *\'zmirror* scrub\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

<!-- -->

**\--cancel**

:   # COMMAND *\'zmirror* list\'

usage: zmirror list \[-h\] \[\--socket-path SOCKET_PATH\] \[\--keys
KEYS\] \[\--no_headers\] \[\--format
{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}\]
\[\--sort
{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}\]
{overdue,scrub,trim,update} \...

# POSITIONAL ARGUMENTS *\'zmirror list\'*

**zmirror list** *overdue*

:   list all overdue devices

**zmirror list** *scrub*

:   list devices based on current/last scrub state

**zmirror list** *trim*

:   list devices based on current/last trim state

**zmirror list** *update*

:   list devices based on when they were last up-to-date

# COMMAND *\'zmirror* list overdue\'

usage: zmirror list overdue \[-h\] \[\--keys KEYS\] \[\--no_headers\]
\[\--format
{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}\]
\[\--sort
{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}\]

# OPTIONS *\'zmirror* list overdue\'

**\--keys** *KEYS*

:   only output this list of keys (columns)

<!-- -->

**\--no_headers**

:   do not print headers when outputting a table

<!-- -->

**\--format** *{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}*

:   either \`json\` or one of the formats defined by the tabulate
    library (see https://https://pypi.org/project/tabulate/#description)

<!-- -->

**\--sort** *{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}*

:   the key (column) to sort for

# COMMAND *\'zmirror* list scrub\'

usage: zmirror list scrub \[-h\] {overdue} \...

# POSITIONAL ARGUMENTS *\'zmirror list scrub\'*

**zmirror list scrub** *overdue*

:   list devices on which a scrub is overdue

# COMMAND *\'zmirror* list scrub overdue\'

usage: zmirror list scrub overdue \[-h\] \[\--keys KEYS\]
\[\--no_headers\] \[\--format
{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}\]
\[\--sort
{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}\]

# OPTIONS *\'zmirror* list scrub overdue\'

**\--keys** *KEYS*

:   only output this list of keys (columns)

<!-- -->

**\--no_headers**

:   do not print headers when outputting a table

<!-- -->

**\--format** *{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}*

:   either \`json\` or one of the formats defined by the tabulate
    library (see https://https://pypi.org/project/tabulate/#description)

<!-- -->

**\--sort** *{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}*

:   the key (column) to sort for

# COMMAND *\'zmirror* list trim\'

usage: zmirror list trim \[-h\] {overdue} \...

# POSITIONAL ARGUMENTS *\'zmirror list trim\'*

**zmirror list trim** *overdue*

:   list devices on which a trim is overdue

# COMMAND *\'zmirror* list trim overdue\'

usage: zmirror list trim overdue \[-h\] \[\--keys KEYS\]
\[\--no_headers\] \[\--format
{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}\]
\[\--sort
{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}\]

# OPTIONS *\'zmirror* list trim overdue\'

**\--keys** *KEYS*

:   only output this list of keys (columns)

<!-- -->

**\--no_headers**

:   do not print headers when outputting a table

<!-- -->

**\--format** *{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}*

:   either \`json\` or one of the formats defined by the tabulate
    library (see https://https://pypi.org/project/tabulate/#description)

<!-- -->

**\--sort** *{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}*

:   the key (column) to sort for

# COMMAND *\'zmirror* list update\'

usage: zmirror list update \[-h\] {overdue} \...

# POSITIONAL ARGUMENTS *\'zmirror list update\'*

**zmirror list update** *overdue*

:   list devices which need updating of their data

# COMMAND *\'zmirror* list update overdue\'

usage: zmirror list update overdue \[-h\] \[\--keys KEYS\]
\[\--no_headers\] \[\--format
{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}\]
\[\--sort
{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}\]

# OPTIONS *\'zmirror* list update overdue\'

**\--keys** *KEYS*

:   only output this list of keys (columns)

<!-- -->

**\--no_headers**

:   do not print headers when outputting a table

<!-- -->

**\--format** *{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}*

:   either \`json\` or one of the formats defined by the tabulate
    library (see https://https://pypi.org/project/tabulate/#description)

<!-- -->

**\--sort** *{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}*

:   the key (column) to sort for

# OPTIONS *\'zmirror* list\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

<!-- -->

**\--keys** *KEYS*

:   only output this list of keys (columns)

<!-- -->

**\--no_headers**

:   do not print headers when outputting a table

<!-- -->

**\--format** *{json,plain,simple,github,grid,simple_grid,rounded_grid,heavy_grid,mixed_grid,double_grid,fancy_grid,outline,simple_outline,rounded_outline,heavy_outline,mixed_outline,double_outline,fancy_outline,pipe,orgtbl,asciidoc,jira,presto,pretty,psql,rst,mediawiki,moinmoin,youtrack,html,unsafehtml,latex,latex_raw,latex_booktabs,latex_longtable,textile,tsv}*

:   either \`json\` or one of the formats defined by the tabulate
    library (see https://https://pypi.org/project/tabulate/#description)

<!-- -->

**\--sort** *{id,last_online,last_update,update_overdue,last_trim,trim_overdue,last_scrub,scrub_overdue}*

:   the key (column) to sort for

# COMMAND *\'zmirror* enable\'

usage: zmirror enable \[-h\] \[\--socket-path SOCKET_PATH\]
{commands,log-events} \...

# POSITIONAL ARGUMENTS *\'zmirror enable\'*

**zmirror enable** *commands*

:   enable command execution

**zmirror enable** *log-events*

:   enable logging of all UDEV and ZED events received by zmirror

# COMMAND *\'zmirror* enable commands\'

usage: zmirror enable commands \[-h\]

# COMMAND *\'zmirror* enable log-events\'

usage: zmirror enable log-events \[-h\]

# OPTIONS *\'zmirror* enable\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* disable\'

usage: zmirror disable \[-h\] \[\--socket-path SOCKET_PATH\]
{commands,log-events} \...

# POSITIONAL ARGUMENTS *\'zmirror disable\'*

**zmirror disable** *commands*

:   disable command execution

**zmirror disable** *log-events*

:   disable logging of all UDEV and ZED events received by zmirror

# COMMAND *\'zmirror* disable commands\'

usage: zmirror disable commands \[-h\]

# COMMAND *\'zmirror* disable log-events\'

usage: zmirror disable log-events \[-h\]

# OPTIONS *\'zmirror* disable\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* set\'

usage: zmirror set \[-h\] \[\--socket-path SOCKET_PATH\]
{log-level,timeout} \...

# POSITIONAL ARGUMENTS *\'zmirror set\'*

**zmirror set** *log-level*

:   temporarily set log level to one of: trace \| debug \| verbose \|
    info \| warning \| error \| critical

**zmirror set** *timeout*

:   temporarily set request timeout in seconds

# COMMAND *\'zmirror* set log-level\'

usage: zmirror set log-level \[-h\] value

**value**

:   the new value of the property

# COMMAND *\'zmirror* set timeout\'

usage: zmirror set timeout \[-h\] value

**value**

:   the new value of the property

# OPTIONS *\'zmirror* set\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# COMMAND *\'zmirror* get\'

usage: zmirror get \[-h\] \[\--socket-path SOCKET_PATH\]
{commands,log-events,log-level,timeout} \...

# POSITIONAL ARGUMENTS *\'zmirror get\'*

**zmirror get** *commands*

:   get command execution

**zmirror get** *log-events*

:   get logging of all UDEV and ZED events received by zmirror

**zmirror get** *log-level*

:   

    **zmirror get** *timeout*

    :   # COMMAND *\'zmirror* get commands\'

usage: zmirror get commands \[-h\]

# COMMAND *\'zmirror* get log-events\'

usage: zmirror get log-events \[-h\]

# COMMAND *\'zmirror* get log-level\'

usage: zmirror get log-level \[-h\]

# COMMAND *\'zmirror* get timeout\'

usage: zmirror get timeout \[-h\]

# OPTIONS *\'zmirror* get\'

**\--socket-path** *SOCKET_PATH*

:   the path to the unix socket on which \`zmirror daemon\` listens, to
    which \`zmirror-trigger\` sends UDEV and ZED events, and to which
    commands are sent when you invoke \`zmirror \<command\>\`. May be
    set via the environment variable \`ZMIRROR_SOCKET_PATH\`. Defaults
    to \`/run/zmirror/zmirror.socket\`

# OPTIONS

**\--version**

:   print the version
