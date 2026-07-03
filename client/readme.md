# tudo

A colorful terminal dashboard that shows your system info, network info, todos
and ideas at a glance.

## Layout

```
SYSTEM   | NETWORK
TODOS    | IDEAS
```

Each section is rendered in a bordered, colored panel. If the terminal isn't
wide enough to fit two columns side by side, all four sections stack into a
single column automatically.

## Installation

Install the `tudo`, `todo` and `idea` commands onto your `PATH`:

```console
./install.sh
```

This installs the app for the current user (no root needed) under
`~/.local/share/tudo/app` (its own virtual environment + a copy of `src/`),
and places three launcher scripts in `~/.local/bin`:

- `tudo` - shows the dashboard
- `todo` - manage todos directly (no `tudo` prefix needed)
- `idea` - manage ideas directly (no `tudo` prefix needed)

If `~/.local/bin` isn't already on your `PATH`, the installer adds it to
both `~/.bashrc` and `~/.zshrc` automatically (creating whichever one
doesn't exist yet), so `tudo`/`todo`/`idea` work regardless of which shell
you use. Open a new shell, or `source` one of those files, afterwards.

For a machine-wide install instead (under `/opt/tudo` and `/usr/local/bin`):

```console
sudo ./install.sh --system
```

To remove everything the installer added:

```console
./uninstall.sh          # or: sudo ./uninstall.sh --system
```

If you have a local todos/ideas database, it'll ask whether to delete it too
(kept by default). Use `--purge-data` or `--keep-data` to skip the prompt:

```console
./uninstall.sh --purge-data     # also delete ~/.local/share/tudo/tudo.db
./uninstall.sh --keep-data      # uninstall the app, keep the database
```

## Usage

Run with no arguments to show the dashboard:

```console
tudo
```

(While developing from source without installing, use `python src/main.py`
instead of `tudo`, `python src/todo_entry.py` instead of `todo`, and
`python src/idea_entry.py` instead of `idea`.)

### Managing todos

Text doesn't need quotes - just type the words after the command (and any
flags), they're joined automatically:

```console
todo add Buy milk
todo done 1
todo undone 1
todo remove 1
todo list
todo list --far      # also show todos due more than 7 days out
todo history         # todos completed in the last 7 days
todo history 5       # todos completed in the last 5 days
```

(These are also reachable as `tudo todo ...`, e.g. `tudo todo add Buy milk`.)

All todo dates use the **Jalali (Persian/Iranian, Hijri-Shamsi) calendar**.
A todo's date/time is entirely optional, and can be set in one of three
mutually-exclusive ways:

| Flag | Alias | Meaning |
| --- | --- | --- |
| `--date VALUE` | `-D` | An explicit Jalali date (see below) |
| `--day N` | `-d` | N days from today |
| `--hour N` | `-h` | N hours from now (sets both date and time) |

```console
todo add --day 3 Buy milk       # 3 days from today
todo add -d 3 Buy milk          # same, short flag
todo add --hour 5 Call mom      # 5 hours from now (date+time)
todo add -h 5 Call mom          # same, short flag
todo add --date 18 Pay rent     # see "nearest date" rules below
todo add -D 3/12 Renew license  # same flag, short alias
```

`--date` accepts:
- `today` / `tomorrow`
- `D` - the nearest day with that day-of-month: this month if it hasn't
  happened yet, otherwise next month. E.g. if today is day 15: `--date 18`
  means the 18th of *this* month, `--date 10` means the 10th of *next*
  month (since the 10th already passed this month).
- `D/M` - the nearest day/month: this year if it hasn't happened yet,
  otherwise next year. E.g. if today is 15/11: `--date 3/4` means 3/4 of
  *next* year (month 4 is already behind month 11), `--date 3/12` means
  3/12 of *this* year (month 12 is still ahead).
- `D/M/Y` - an explicit date, used as-is.

#### Dashboard / list grouping

Todos are grouped and separated with a divider line, in this order:

1. Todos with no date (oldest added first)
2. Today (including anything overdue)
3. Tomorrow
4. The next 7 days
5. A single line with the count of todos due after that (use
   `todo list --far` to list them in full instead of just a count)

Todos that are overdue, or whose time-of-day has already passed today and
are still not done, are highlighted in bold red.

#### Completed todos

Marking a todo `done` keeps it visible (with a strikethrough) in the
dashboard/list for **24 hours**, after which it's only visible via
`todo history`.

### Managing ideas

Ideas work the same way, minus the dates:

```console
idea add Build a rocket
idea done 1
idea undone 1
idea remove 1
idea list
idea history
idea history 5
```

(These are also reachable as `tudo idea ...`, e.g. `tudo idea add Build a rocket`.)

Completed ideas follow the same 24-hour visibility / history rule as todos.

## Multi-device syncing

If you run a tudo server (see `../server/readme.md`), you can sync your
todos/ideas across multiple devices (all belonging to the same person -
syncing is not designed for sharing lists between different users).

```console
./connect_to_server.sh      # turn syncing on, interactively
./disconnect_server.sh      # turn syncing off
```

`connect_to_server.sh` asks for the server's address (e.g. `127.0.0.1:8000`
for a local server, or `tudo.jsezar.ir` for one behind your own reverse
proxy) and an optional API key, then:

- appends `/api/` to build the base API URL,
- verifies the server is reachable,
- saves the config to `~/.config/tudo/sync.json`,
- installs a background job (a `systemd --user` timer, falling back to
  `cron`) that syncs every 5 minutes.

Once enabled, syncing is designed to never slow down a command:

- Adding/completing/removing a todo or idea immediately kicks off a sync in
  a **separate, detached background process** - the command itself returns
  right away, it never waits for the network.
- Viewing the dashboard or a list opportunistically triggers a background
  sync too (at most once every 60 seconds), but always renders instantly
  using whatever data is already stored locally - it never waits for that
  sync to finish either.
- The background timer covers the rest: even if you don't touch the CLI for
  a while, it still syncs (and retries anything that previously failed to
  push) every 5 minutes.
- If a sync attempt fails (e.g. the server is unreachable), it is **not**
  retried immediately - tudo just waits for the next trigger. Nothing is
  lost: unsynced changes stay queued locally.

Run `tudo sync` any time to trigger a sync immediately and wait for the
result - handy right after running `connect_to_server.sh`, or to debug
connectivity.

When syncing is enabled, the dashboard and `todo list`/`idea list` show when
the last successful sync happened, e.g. `↻ Last synced: 3 minutes ago`.

### How conflicts are resolved

Each todo/idea has a globally unique id and an `updated_at` timestamp used
for last-write-wins conflict resolution: if the same item was changed on two
devices while one was offline, the most recent change wins once they sync,
and every device converges to the same result. Deletions are synced too
(as tombstones), so removing something on one device removes it everywhere.

## Live-refreshing view

`runner.sh` clears the screen and redraws the dashboard every 5 seconds:

```console
./runner.sh
```

## Data storage

Todos and ideas are stored in a local SQLite database at
`$XDG_DATA_HOME/tudo/tudo.db` (defaults to `~/.local/share/tudo/tudo.db`).

## Project structure

- `src/main.py` - entry point for the `tudo` command (dashboard)
- `src/todo_entry.py` - entry point for the standalone `todo` command
- `src/idea_entry.py` - entry point for the standalone `idea` command
- `src/cli.py` - cyclopts CLI commands (`todo` / `idea` subcommands + default dashboard)
- `src/dashboard.py` - builds the rich panels, grouping/sorting and the responsive 2-column/1-column layout
- `src/db.py` - SQLite persistence for todos and ideas (including 24h visibility, history queries, and the sync outbox/tombstones)
- `src/persian_date.py` - Jalali (Persian) calendar parsing/formatting helpers
- `src/device.py` - stable per-installation device id, used for sync conflict resolution
- `src/sync_config.py` - reads/writes `~/.config/tudo/sync.json`
- `src/sync_worker.py` - performs one push+pull sync round-trip with the server (run standalone or spawned in the background)
- `src/sync_trigger.py` - decides when to spawn a background sync, without ever blocking a command
- `install.sh` / `uninstall.sh` - install/remove the `tudo`, `todo`, `idea` commands
- `connect_to_server.sh` / `disconnect_server.sh` - turn multi-device syncing on/off
- `src/system_info.py` - hostname/uptime/cpu/ram/disk stats
- `src/network_info.py` - network interface IP addresses
