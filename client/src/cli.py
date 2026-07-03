"""Command line interface for tudo, built with cyclopts."""

from __future__ import annotations

from typing import Annotated, Optional

import dashboard
import db
import persian_date as pdate
import sync_config
import sync_trigger
import sync_worker
from cyclopts import App, Parameter
from rich.console import Console

console = Console()

app = App(
    name="tudo",
    help="A colorful terminal dashboard for your system, network, todos and ideas.",
)

# "-h" is freed up from the help flags on the `todo` app so it can be used as
# the shorthand for --hour on `todo add`.
todo_app = App(name="todo", help="Manage your todos.", help_flags=["--help"])
idea_app = App(name="idea", help="Manage your ideas.")
app.command(todo_app)
app.command(idea_app)


@app.default
def show_dashboard():
    """Show the tudo dashboard (system, network, todos and ideas)."""
    db.init_db()
    sync_trigger.before_read()
    dashboard.render_dashboard(console)


@app.command(name="sync")
def manual_sync():
    """Immediately sync with the server (waits for the result)."""
    if not sync_config.is_enabled():
        console.print(
            "[yellow]Syncing is not enabled.[/yellow] Run ./connect_to_server.sh to enable it."
        )
        raise SystemExit(1)

    db.init_db()
    with console.status("Syncing..."):
        ok = sync_worker.run_sync()

    if ok:
        console.print("[green]Synced successfully.[/green]")
    else:
        error = sync_config.load_config().get("last_sync_error")
        if error:
            console.print(f"[bold red]Sync failed:[/bold red] {error}")
        else:
            console.print(
                "[bold red]Sync failed[/bold red] (server unreachable, or another sync is already running)."
            )
        raise SystemExit(1)


def _resolve_todo_due(
    date: Optional[str], day: Optional[int], hour: Optional[int]
) -> tuple[Optional[str], Optional[str]]:
    """Turn the --date/--day/--hour options into (due_date, due_time) storage strings."""
    provided = [
        name
        for name, value in (("--date", date), ("--day", day), ("--hour", hour))
        if value is not None
    ]
    if len(provided) > 1:
        raise ValueError(
            f"Only one of --date/-D, --day/-d, --hour/-h can be used at a time (got {', '.join(provided)})."
        )

    if hour is not None:
        dt = pdate.add_hours(hour)
        return pdate.to_storage_date(dt.date()), pdate.to_storage_time(dt.time())
    if day is not None:
        d = pdate.add_days(day)
        return pdate.to_storage_date(d), None
    if date is not None:
        d = pdate.parse_date_flag(date)
        return pdate.to_storage_date(d), None
    return None, None


# --------------------------------------------------------------------------
# Todos
# --------------------------------------------------------------------------


@todo_app.command(name="add")
def todo_add(
    *text: str,
    date: Annotated[Optional[str], Parameter(name=["--date", "-D"])] = None,
    day: Annotated[Optional[int], Parameter(name=["--day", "-d"])] = None,
    hour: Annotated[Optional[int], Parameter(name=["--hour", "-h"])] = None,
):
    """Add a new todo. No quotes needed: todo add Buy milk

    Parameters
    ----------
    text: The todo description (multiple words, no quotes needed).
    date: Due date (Jalali). "D", "D/M" or "D/M/Y", or 'today'/'tomorrow'.
    day: Due date is N days from today (Jalali).
    hour: Due date/time is N hours from now (Jalali).
    """
    if not text:
        console.print("[bold red]Error:[/bold red] Please provide the todo text.")
        raise SystemExit(1)

    db.init_db()
    try:
        due_date, due_time = _resolve_todo_due(date, day, hour)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise SystemExit(1)

    todo_text = " ".join(text)
    todo_id = db.add_todo(todo_text, due_date, due_time)

    when = ""
    if due_date:
        when = f" [dim]({pdate.to_display_date(pdate.from_storage_date(due_date))}"
        if due_time:
            when += f" {due_time}"
        when += ")[/dim]"
    console.print(f"[green]Added todo[/green] [dim]#{todo_id}[/dim]: {todo_text}{when}")
    sync_trigger.after_mutation()


@todo_app.command(name="done")
def todo_done(id: int):
    """Mark a todo as done."""
    db.init_db()
    if db.set_todo_done(id, True):
        console.print(f"[green]Todo #{id} marked as done.[/green]")
        sync_trigger.after_mutation()
    else:
        console.print(f"[bold red]No todo found with id {id}.[/bold red]")


@todo_app.command(name="undone")
def todo_undone(id: int):
    """Mark a todo as not done."""
    db.init_db()
    if db.set_todo_done(id, False):
        console.print(f"[yellow]Todo #{id} marked as not done.[/yellow]")
        sync_trigger.after_mutation()
    else:
        console.print(f"[bold red]No todo found with id {id}.[/bold red]")


@todo_app.command(name="remove")
def todo_remove(id: int):
    """Remove a todo."""
    db.init_db()
    if db.remove_todo(id):
        console.print(f"[green]Todo #{id} removed.[/green]")
        sync_trigger.after_mutation()
    else:
        console.print(f"[bold red]No todo found with id {id}.[/bold red]")


@todo_app.command(name="list")
def todo_list(far: Annotated[bool, Parameter(name=["--far", "-f"])] = False):
    """List all todos.

    Parameters
    ----------
    far: Also list todos due more than 7 days from now (instead of just a count).
    """
    db.init_db()
    sync_trigger.before_read()
    dashboard.render_todos(console, show_far=far)


@todo_app.command(name="history")
def todo_history(days: int = 7):
    """Show todos completed in the last N days (default: 7).

    Parameters
    ----------
    days: How many days back to look.
    """
    db.init_db()
    sync_trigger.before_read()
    dashboard.render_todo_history(days, console)


# --------------------------------------------------------------------------
# Ideas
# --------------------------------------------------------------------------


@idea_app.command(name="add")
def idea_add(*text: str):
    """Add a new idea. No quotes needed: idea add Build a rocket

    Parameters
    ----------
    text: The idea description (multiple words, no quotes needed).
    """
    if not text:
        console.print("[bold red]Error:[/bold red] Please provide the idea text.")
        raise SystemExit(1)

    db.init_db()
    idea_text = " ".join(text)
    idea_id = db.add_idea(idea_text)
    console.print(f"[magenta]Added idea[/magenta] [dim]#{idea_id}[/dim]: {idea_text}")
    sync_trigger.after_mutation()


@idea_app.command(name="done")
def idea_done(id: int):
    """Mark an idea as done."""
    db.init_db()
    if db.set_idea_done(id, True):
        console.print(f"[green]Idea #{id} marked as done.[/green]")
        sync_trigger.after_mutation()
    else:
        console.print(f"[bold red]No idea found with id {id}.[/bold red]")


@idea_app.command(name="undone")
def idea_undone(id: int):
    """Mark an idea as not done."""
    db.init_db()
    if db.set_idea_done(id, False):
        console.print(f"[yellow]Idea #{id} marked as not done.[/yellow]")
        sync_trigger.after_mutation()
    else:
        console.print(f"[bold red]No idea found with id {id}.[/bold red]")


@idea_app.command(name="remove")
def idea_remove(id: int):
    """Remove an idea."""
    db.init_db()
    if db.remove_idea(id):
        console.print(f"[green]Idea #{id} removed.[/green]")
        sync_trigger.after_mutation()
    else:
        console.print(f"[bold red]No idea found with id {id}.[/bold red]")


@idea_app.command(name="list")
def idea_list():
    """List all ideas."""
    db.init_db()
    sync_trigger.before_read()
    dashboard.render_ideas(console)


@idea_app.command(name="history")
def idea_history(days: int = 7):
    """Show ideas completed in the last N days (default: 7).

    Parameters
    ----------
    days: How many days back to look.
    """
    db.init_db()
    sync_trigger.before_read()
    dashboard.render_idea_history(days, console)
