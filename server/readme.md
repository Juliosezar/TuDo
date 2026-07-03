# tudo server

A small FastAPI server that lets multiple devices belonging to the same
person sync their tudo todos/ideas, and exposes a plain CRUD API for
scripting/AI-agent use.

## Running it

```console
cp .env.example .env    # then edit TUDO_API_KEY (recommended) and TUDO_PORT
docker compose up -d --build
```

This builds the image and starts the API bound to `127.0.0.1:${TUDO_PORT}`
(default `8000`) **on the host's loopback interface only** - it is never
exposed to the network directly. If you want to reach it from other
machines (e.g. hosting it on a VPS so your phone/laptop can sync), put your
own reverse proxy (nginx, Caddy, etc.) with TLS in front of
`127.0.0.1:${TUDO_PORT}`. That's outside the scope of this project.

Data is persisted in a Docker volume (`tudo_data`), independent of the
container's lifecycle.

To stop it: `docker compose down` (add `-v` to also delete the volume/data).

## Authentication

If `TUDO_API_KEY` is set (recommended for anything beyond pure localhost
use), every request except `GET /api/health` must include:

```
Authorization: Bearer <TUDO_API_KEY>
```

If it's left empty, the API is open - fine only if it's truly unreachable
from outside your machine.

## API

### Sync protocol

- `POST /api/sync/` - the sync protocol used by the client's
  `sync_worker.py`. Clients push their local pending changes (tagged with a
  device id and an `updated_at` timestamp) and their last-known sequence
  number; the server merges everything using last-write-wins (by
  `updated_at`, tie-broken by `device_id`) and returns everything the client
  is missing, plus a new sequence number to remember for next time.

### Plain CRUD (for direct use - scripts, curl, an AI agent, etc.)

This is independent of the sync protocol; it mirrors everything the
terminal client can do.

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

## Data model / conflict resolution

Every record is identified by a client-generated UUID (not the CLI's local
numeric id, which only exists for convenient typing on one device) and
carries an `updated_at` timestamp + `device_id`. When two devices edit the
same record while offline, the version with the later `updated_at` wins on
both sides once they sync - this is a deliberate simplification
(whole-record last-write-wins rather than per-field merging), which is a
reasonable trade-off for a personal, single-user, low-conflict-rate todo
list. Deletions are soft (tombstoned) so they can propagate to other
devices instead of just disappearing silently.

## Project structure

- `app/main.py` - FastAPI app setup, `/api/health`
- `app/routers/todos.py`, `app/routers/ideas.py` - plain CRUD endpoints
- `app/routers/sync.py` - the sync protocol endpoint
- `app/db.py` - SQLite persistence + the last-write-wins merge logic
- `app/schemas.py` - pydantic request/response models
- `app/auth.py` - optional bearer-token auth
- `app/config.py` - environment-variable configuration
