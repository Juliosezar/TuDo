# tudo

A colorful terminal dashboard for your system info, network info, todos and
ideas - with an optional self-hosted server so the same todos/ideas can be
synced across all of your own devices.

```
SYSTEM   | NETWORK
TODOS    | IDEAS
```

Every section is rendered in a bordered, colored panel. If the terminal
isn't wide enough for two columns, everything stacks into one column
automatically.

This repository has two parts:

- **`client/`** - the terminal app itself: a Python CLI (`tudo`, `todo`,
  `idea`) backed by a local SQLite database. This is all you need to use
  tudo on a single machine.
- **`server/`** - an optional, self-hosted FastAPI server (run with Docker)
  that lets multiple devices belonging to *you* keep their todos/ideas in
  sync. Not required unless you want multi-device syncing.

This file is a full walkthrough of installing and using both. For quick
reference, `client/readme.md` and `server/readme.md` cover the same ground
in more detail, scoped to each part.

## Table of contents

- [Features](#features)
- [Client: installation](#client-installation)
- [Client: usage](#client-usage)
  - [Managing todos](#managing-todos)
  - [Managing ideas](#managing-ideas)
  - [Live-refreshing view](#live-refreshing-view)
- [Server: installation](#server-installation)
- [Server: API](#server-api)
- [Multi-device syncing](#multi-device-syncing)
- [Data storage](#data-storage)
- [Running from source (development)](#running-from-source-development)
- [Project structure](#project-structure)

## Features

- System info (hostname, uptime, CPU, RAM, disk usage) and network info
  (interfaces + IPs), refreshed every time you run `tudo`.
- Todos with optional due date **and time**, using the **Jalali
  (Persian/Iranian, Hijri-Shamsi) calendar**.
- Ideas (no dates, just quick capture).
- No quotes needed when adding: `todo add Buy milk` just works.
- A responsive 2-column/1-column layout that adapts to your terminal width.
- Completed items stick around (struck through) for 24 hours, then move to
  `history`.
- Optional multi-device sync via a self-hosted server, designed to never
  slow down a command (see [Multi-device syncing](#multi-device-syncing)).
- A plain REST API on the server for scripting or hooking up an AI agent.

## Client: installation

Requires Python 3.10+ on Linux.

```console
cd client
./install.sh
```

This creates a dedicated virtual environment and copies the app to
`~/.local/share/tudo/app`, then installs three commands to `~/.local/bin`:

| Command | What it does |
| --- | --- |
| `tudo` | Shows the dashboard |
| `todo` | Manage todos directly |
| `idea` | Manage ideas directly |

If `~/.local/bin` isn't already on your `PATH`, the installer adds it to
both `~/.bashrc` and `~/.zshrc` for you (creating whichever one doesn't
exist yet), so `tudo`/`todo`/`idea` work regardless of which shell you use.
Open a new shell, or `source` one of those files, afterwards.

For a machine-wide install instead (under `/opt/tudo` and
`/usr/local/bin`, requires root):

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

## Client: usage

Run with no arguments to show the dashboard:

```console
tudo
```

### Managing todos

Text doesn't need quotes - just type the words after the command (and any
flags); they're joined automatically:

```console
todo add Buy milk
todo done 1
todo undone 1
todo remove 1
todo list
todo list --far      # also show todos due more than 7 days out (instead of just a count)
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

Todos are grouped in the dashboard/list, separated with a divider line, in
this order:

1. Todos with no date (oldest added first)
2. Today (including anything overdue)
3. Tomorrow
4. The next 7 days
5. A single line with the count of todos due after that (use
   `todo list --far` to list them in full instead of just a count)

Todos that are overdue, or whose time-of-day has already passed today and
are still not done, are highlighted in bold red.

Marking a todo `done` keeps it visible (struck through) in the
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

### Live-refreshing view

`runner.sh` clears the screen and redraws the dashboard every 5 seconds,
like a little terminal widget:

```console
cd client
./runner.sh
```

## Server: installation

The server is optional - only needed if you want to sync todos/ideas across
more than one of your own devices. Requires Docker + Docker Compose.

```console
cd server
cp .env.example .env    # edit TUDO_API_KEY (recommended) and TUDO_PORT if needed
docker compose up -d --build
```

This builds the image and starts the API bound to `127.0.0.1:${TUDO_PORT}`
(default `8000`) **on the host's loopback interface only** - by design, it
is never exposed to the network directly. If you want to reach it from
other machines (e.g. hosting it on a VPS so your phone/laptop can sync),
put your own reverse proxy (nginx, Caddy, etc.) with TLS in front of
`127.0.0.1:${TUDO_PORT}` - that part is up to you.

Data is persisted in a Docker volume (`tudo_data`), independent of the
container's lifecycle.

```console
docker compose down          # stop it (data is kept)
docker compose down -v       # stop it and delete all data
```

### Authentication

If `TUDO_API_KEY` is set in `.env` (recommended for anything beyond pure
localhost use), every request except `GET /api/health` must include:

```
Authorization: Bearer <TUDO_API_KEY>
```

Leave it empty only if the server is truly unreachable from outside your
own machine.

## Server: API

### Sync protocol

- `POST /api/sync/` - used by the client's background sync worker. A
  client pushes its pending local changes (each tagged with a device id and
  an `updated_at` timestamp) plus the last sequence number it has seen; the
  server merges everything with last-write-wins (by `updated_at`, tie-broken
  by `device_id`) and returns everything the client is missing, plus a new
  sequence number to remember for next time.

### Plain CRUD

Independent of the sync protocol - useful for scripts, curl, or hooking up
an AI agent. Mirrors everything the terminal client can do:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/todo/` | Create a todo (`text`, optional `due_date`/`due_time`) |
| `GET` | `/api/todo/` | List todos (`?include_done=false` to hide completed ones) |
| `GET` | `/api/todo/history?days=7` | Todos completed in the last N days |
| `GET` | `/api/todo/{uuid}` | Get a single todo |
| `POST` | `/api/todo/{uuid}/done` | Mark a todo done |
| `POST` | `/api/todo/{uuid}/undone` | Mark a todo not done |
| `DELETE` | `/api/todo/{uuid}` | Remove a todo (soft delete) |
| `POST` | `/api/idea/` | Create an idea (`text`) |
| `GET` | `/api/idea/` | List ideas (`?include_done=false` to hide completed ones) |
| `GET` | `/api/idea/history?days=7` | Ideas completed in the last N days |
| `GET` | `/api/idea/{uuid}` | Get a single idea |
| `POST` | `/api/idea/{uuid}/done` | Mark an idea done |
| `POST` | `/api/idea/{uuid}/undone` | Mark an idea not done |
| `DELETE` | `/api/idea/{uuid}` | Remove an idea (soft delete) |
| `GET` | `/api/health` | Unauthenticated connectivity check |

Interactive API docs are available at `/docs` (Swagger UI) once the server
is running.

## Multi-device syncing

Once a server is running (see above), turn on syncing from any client
device:

```console
cd client
./connect_to_server.sh      # turn syncing on, interactively
./disconnect_server.sh      # turn syncing off
```

`connect_to_server.sh` asks for:

- **Server address** - e.g. `127.0.0.1:8000` for a local server, or
  `tudo.jsezar.ir` for one behind your own reverse proxy. `/api/` is
  appended automatically to build the full API URL.
- **API key** (optional) - whatever you set as `TUDO_API_KEY` on the
  server.

It then verifies the server is reachable, saves the config to
`~/.config/tudo/sync.json`, and installs a background job (a `systemd
--user` timer, falling back to `cron`) that syncs every 5 minutes.

Syncing is designed to **never** slow a command down:

- Adding/completing/removing a todo or idea immediately kicks off a sync in
  a separate, detached background process - the command itself returns
  right away and never waits on the network.
- Viewing the dashboard or a list opportunistically triggers a background
  sync too (at most once every 60 seconds), but always renders instantly
  using whatever data is already stored locally.
- A periodic background job covers the rest: even if you don't touch the
  CLI for a while, it still syncs (and retries anything that previously
  failed to push) every 5 minutes.
- If a sync attempt fails (e.g. the server is unreachable), it is **not**
  retried immediately - tudo just waits for the next trigger. Nothing is
  lost: unsynced changes stay queued locally until the next successful sync.

Run `tudo sync` any time to trigger a sync immediately and wait for the
result - handy right after `connect_to_server.sh`, or to debug connectivity.

When syncing is enabled, the dashboard and `todo list`/`idea list` show when
the last successful sync happened, e.g. `↻ Last synced: 3 minutes ago`.

To disconnect a device from the server:

```console
./disconnect_server.sh
```

This removes the background job and the local sync config. Your local
todos/ideas and everything already on the server are left untouched - it
only stops *that device* from syncing.

### How conflicts are resolved

Every todo/idea has a globally unique id (in addition to the small local
number used for typing commands, which only makes sense on one device) and
an `updated_at` timestamp used for last-write-wins conflict resolution: if
the same item was changed on two devices while one was offline, the most
recent change wins once they sync, and every device converges to the same
result. Deletions are synced too (as tombstones), so removing something on
one device removes it everywhere. This is a deliberate simplification
(whole-record last-write-wins, not per-field merging) - a reasonable
trade-off for a personal, single-user, low-conflict-rate todo list.

Syncing is designed for **one person's own devices**, not for sharing lists
between different people.

## Data storage

| What | Where |
| --- | --- |
| Todos/ideas (local SQLite database) | `$XDG_DATA_HOME/tudo/tudo.db` (defaults to `~/.local/share/tudo/tudo.db`) |
| Device id (stable per installation) | `~/.config/tudo/device_id` |
| Sync configuration | `~/.config/tudo/sync.json` |
| Server data (inside Docker) | Docker volume `tudo_data` |

## Running from source (development)

You don't need to run `install.sh` to try the client - from `client/`:

```console
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python src/main.py            # same as the installed `tudo` command
.venv/bin/python src/todo_entry.py      # same as the installed `todo` command
.venv/bin/python src/idea_entry.py      # same as the installed `idea` command
```

`connect_to_server.sh` and `disconnect_server.sh` also work against a
source checkout (they fall back to `client/.venv` if no installed copy is
found under `/opt/tudo` or `~/.local/share/tudo/app`).

For the server, see [Server: installation](#server-installation) - it
always runs the same way (via Docker), whether you're developing or
deploying it.

## Project structure

```
Tudo/
├── client/
│   ├── src/
│   │   ├── main.py            entry point for `tudo` (dashboard)
│   │   ├── todo_entry.py      entry point for standalone `todo`
│   │   ├── idea_entry.py      entry point for standalone `idea`
│   │   ├── cli.py             cyclopts CLI commands
│   │   ├── dashboard.py       rich panels, grouping/sorting, responsive layout
│   │   ├── db.py              SQLite persistence (todos/ideas, sync outbox/tombstones)
│   │   ├── persian_date.py    Jalali (Persian) calendar helpers
│   │   ├── device.py          stable per-installation device id
│   │   ├── sync_config.py     reads/writes ~/.config/tudo/sync.json
│   │   ├── sync_worker.py     one push+pull sync round-trip with the server
│   │   ├── sync_trigger.py    decides when to fire a background sync
│   │   ├── system_info.py     hostname/uptime/cpu/ram/disk stats
│   │   └── network_info.py    network interface IPs
│   ├── install.sh / uninstall.sh          install/remove tudo, todo, idea
│   ├── connect_to_server.sh / disconnect_server.sh   turn syncing on/off
│   ├── runner.sh               live-refreshing dashboard loop
│   └── requirements.txt
└── server/
    ├── app/
    │   ├── main.py             FastAPI app setup, /api/health
    │   ├── routers/todos.py    plain CRUD for todos
    │   ├── routers/ideas.py    plain CRUD for ideas
    │   ├── routers/sync.py     the sync protocol endpoint
    │   ├── db.py               SQLite persistence + last-write-wins merge logic
    │   ├── schemas.py          pydantic request/response models
    │   ├── auth.py             optional bearer-token auth
    │   └── config.py           environment-variable configuration
    ├── Dockerfile
    ├── docker-compose.yml
    ├── .env.example
    └── requirements.txt
```
