"""Builds and renders the tudo dashboard using rich."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import db
import network_info
import persian_date as pdate
import sync_config
import system_info
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

SYSTEM_COLOR = "cyan"
NETWORK_COLOR = "green"
TODO_COLOR = "yellow"
IDEA_COLOR = "magenta"

# Extra horizontal space reserved for gutters/padding when checking whether
# two panels fit side by side.
COLUMN_GUTTER = 4

FAR_FUTURE_DAYS = 7


def _percent_style(percent: float) -> str:
    if percent < 60:
        return "green"
    if percent < 85:
        return "yellow"
    return "red"


def build_system_panel() -> Panel:
    table = Table.grid(padding=(0, 1))
    table.add_column(style=f"bold {SYSTEM_COLOR}", no_wrap=True)
    table.add_column()

    hostname = system_info.get_hostname()
    uptime = system_info.get_uptime()
    cpu = system_info.get_cpu_percent()
    used_ram, total_ram, ram_percent = system_info.get_ram_info()

    table.add_row("hostname", hostname)
    table.add_row("uptime", uptime)
    table.add_row("cpu", f"[{_percent_style(cpu)}]{cpu:.2f}%[/{_percent_style(cpu)}]")
    table.add_row(
        "ram",
        f"{used_ram:.0f}GB / {total_ram:.0f}GB "
        f"([{_percent_style(ram_percent)}]{ram_percent:.0f}%[/{_percent_style(ram_percent)}])",
    )
    table.add_row("disk", "")
    for path in system_info.DISK_PATHS:
        used, total, percent = system_info.get_disk_usage(path)
        table.add_row(
            f"  {path}",
            f"{used:.0f}G used of {total:.0f}G "
            f"([{_percent_style(percent)}]{percent:.0f}%[/{_percent_style(percent)}])",
        )

    return Panel(
        table,
        title="[bold]SYSTEM[/bold]",
        border_style=SYSTEM_COLOR,
        title_align="left",
    )


def build_network_panel() -> Panel:
    interfaces = network_info.get_network_ips()

    if not interfaces:
        content = Text("No active interface found", style="dim italic")
    else:
        table = Table.grid(padding=(0, 1))
        table.add_column(style=f"bold {NETWORK_COLOR}", no_wrap=True)
        table.add_column()
        for ifname, ip in interfaces:
            table.add_row(ifname, ip)
        content = table

    return Panel(
        content,
        title="[bold]NETWORK[/bold]",
        border_style=NETWORK_COLOR,
        title_align="left",
    )


# --------------------------------------------------------------------------
# Todos
# --------------------------------------------------------------------------


@dataclass
class _TodoBuckets:
    no_date: list[db.Todo]
    today: list[db.Todo]
    tomorrow: list[db.Todo]
    next7: list[db.Todo]
    later: list[db.Todo]


def _bucket_todos(todos: list[db.Todo]) -> _TodoBuckets:
    today = pdate.today()
    tomorrow = pdate.add_days(1, today)
    week_end = pdate.add_days(FAR_FUTURE_DAYS, today)

    buckets = _TodoBuckets(no_date=[], today=[], tomorrow=[], next7=[], later=[])

    for todo in todos:
        if not todo.due_date:
            buckets.no_date.append(todo)
            continue
        d = pdate.from_storage_date(todo.due_date)
        if d <= today:
            buckets.today.append(todo)
        elif d == tomorrow:
            buckets.tomorrow.append(todo)
        elif d <= week_end:
            buckets.next7.append(todo)
        else:
            buckets.later.append(todo)

    sort_key = lambda t: (t.due_date or "", t.due_time or "")  # noqa: E731
    buckets.today.sort(key=sort_key)
    buckets.tomorrow.sort(key=sort_key)
    buckets.next7.sort(key=sort_key)
    buckets.later.sort(key=sort_key)

    return buckets


def _todo_is_overdue(todo: db.Todo) -> bool:
    """True when the todo has a due date/time strictly in the past and isn't done."""
    if todo.done or not todo.due_date:
        return False
    d = pdate.from_storage_date(todo.due_date)
    today = pdate.today()
    if d < today:
        return True
    if d == today and todo.due_time:
        due_dt = pdate.jdatetime.datetime.combine(
            d, pdate.from_storage_time(todo.due_time)
        )
        return due_dt < pdate.now()
    return False


def _todo_row(todo: db.Todo) -> tuple[str, str, str, str]:
    today = pdate.today()
    tomorrow = pdate.add_days(1, today)
    d = pdate.from_storage_date(todo.due_date) if todo.due_date else None
    overdue = _todo_is_overdue(todo)

    id_cell = f"[dim]#{todo.id}[/dim]"

    if todo.done:
        mark = "[green]\u2611[/green]"
        text = f"[dim strike]{todo.text}[/dim strike]"
    elif overdue:
        mark = "[bold red]\u2610[/bold red]"
        text = f"[bold red]{todo.text}[/bold red]"
    elif d == today:
        mark = f"[{TODO_COLOR}]\u2610[/{TODO_COLOR}]"
        text = f"[bold yellow]{todo.text}[/bold yellow]"
    elif d == tomorrow:
        mark = f"[{TODO_COLOR}]\u2610[/{TODO_COLOR}]"
        text = f"[cyan]{todo.text}[/cyan]"
    else:
        mark = f"[{TODO_COLOR}]\u2610[/{TODO_COLOR}]"
        text = todo.text

    date_cell = ""
    if d:
        date_str = pdate.to_display_date(d)
        if todo.due_time:
            date_str += f" {todo.due_time}"
        if todo.done:
            date_style = "dim strike"
        elif overdue:
            date_style = "bold red"
        elif d == today:
            date_style = "bold yellow"
        elif d == tomorrow:
            date_style = "cyan"
        else:
            date_style = "dim"
        date_cell = f"[{date_style}]{date_str}[/{date_style}]"

    return id_cell, mark, text, date_cell


def _todos_table(items: list[db.Todo]) -> Table:
    table = Table.grid(padding=(0, 1), expand=True)
    table.add_column(no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(ratio=1)
    table.add_column(no_wrap=True)
    for todo in items:
        table.add_row(*_todo_row(todo))
    return table


def build_todos_panel(show_far: bool = False) -> Panel:
    todos = db.list_todos()

    if not todos:
        content: RenderableType = Text(
            "No todos yet. Add one with: todo add Buy milk", style="dim italic"
        )
        return Panel(
            content,
            title="[bold]TODOS[/bold]",
            border_style=TODO_COLOR,
            title_align="left",
        )

    buckets = _bucket_todos(todos)
    groups: list[RenderableType] = []

    def add_group(items: list[db.Todo]) -> None:
        if not items:
            return
        if groups:
            groups.append(Rule(style="dim"))
        groups.append(_todos_table(items))

    add_group(buckets.no_date)
    add_group(buckets.today)
    add_group(buckets.tomorrow)
    add_group(buckets.next7)

    if buckets.later:
        if show_far:
            add_group(buckets.later)
        else:
            if groups:
                groups.append(Rule(style="dim"))
            count = len(buckets.later)
            word = "todo" if count == 1 else "todos"
            groups.append(
                Text.from_markup(
                    f"[dim italic]+{count} more {word} due after {FAR_FUTURE_DAYS} days "
                    f"(use 'todo list --far' to see them)[/dim italic]"
                )
            )

    content = Group(*groups)
    return Panel(
        content, title="[bold]TODOS[/bold]", border_style=TODO_COLOR, title_align="left"
    )


def render_todos(console: Console | None = None, show_far: bool = False) -> None:
    console = console or Console()
    console.print(build_todos_panel(show_far=show_far))
    _print_sync_status(console)


# --------------------------------------------------------------------------
# Ideas
# --------------------------------------------------------------------------


def _idea_row(idea: db.Idea) -> tuple[str, str, str]:
    if idea.done:
        bullet = "[green]\u2611[/green]"
        text = f"[dim strike]{idea.text}[/dim strike]"
    else:
        bullet = f"[{IDEA_COLOR}]\u2022[/{IDEA_COLOR}]"
        text = idea.text
    return f"[dim]#{idea.id}[/dim]", bullet, text


def build_ideas_panel() -> Panel:
    ideas = db.list_ideas()

    if not ideas:
        content: RenderableType = Text(
            "No ideas yet. Add one with: idea add Build a rocket",
            style="dim italic",
        )
    else:
        table = Table.grid(padding=(0, 1))
        table.add_column(no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(ratio=1)
        for idea in ideas:
            table.add_row(*_idea_row(idea))
        content = table

    return Panel(
        content, title="[bold]IDEAS[/bold]", border_style=IDEA_COLOR, title_align="left"
    )


def render_ideas(console: Console | None = None) -> None:
    console = console or Console()
    console.print(build_ideas_panel())
    _print_sync_status(console)


# --------------------------------------------------------------------------
# History
# --------------------------------------------------------------------------


def render_todo_history(days: int, console: Console | None = None) -> None:
    console = console or Console()
    todos = db.list_todos_history(days)

    if not todos:
        content: RenderableType = Text(
            f"No todos completed in the last {days} day(s).", style="dim italic"
        )
    else:
        table = Table.grid(padding=(0, 1))
        table.add_column(no_wrap=True)
        table.add_column(ratio=1)
        table.add_column(no_wrap=True)
        for todo in todos:
            done_when = (
                pdate.gregorian_to_display_datetime(todo.done_at)
                if todo.done_at
                else ""
            )
            table.add_row(
                "[green]\u2611[/green]",
                f"[dim strike]{todo.text}[/dim strike]",
                f"[dim]{done_when}[/dim]",
            )
        content = table

    console.print(
        Panel(
            content,
            title=f"[bold]TODO HISTORY (last {days} day(s))[/bold]",
            border_style=TODO_COLOR,
            title_align="left",
        )
    )


def render_idea_history(days: int, console: Console | None = None) -> None:
    console = console or Console()
    ideas = db.list_ideas_history(days)

    if not ideas:
        content: RenderableType = Text(
            f"No ideas completed in the last {days} day(s).", style="dim italic"
        )
    else:
        table = Table.grid(padding=(0, 1))
        table.add_column(no_wrap=True)
        table.add_column(ratio=1)
        table.add_column(no_wrap=True)
        for idea in ideas:
            done_when = (
                pdate.gregorian_to_display_datetime(idea.done_at)
                if idea.done_at
                else ""
            )
            table.add_row(
                "[green]\u2611[/green]",
                f"[dim strike]{idea.text}[/dim strike]",
                f"[dim]{done_when}[/dim]",
            )
        content = table

    console.print(
        Panel(
            content,
            title=f"[bold]IDEA HISTORY (last {days} day(s))[/bold]",
            border_style=IDEA_COLOR,
            title_align="left",
        )
    )


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------


def render_dashboard(console: Console | None = None) -> None:
    console = console or Console()

    system_panel = build_system_panel()
    network_panel = build_network_panel()
    todos_panel = build_todos_panel()
    ideas_panel = build_ideas_panel()

    row1_width = (
        console.measure(system_panel).maximum + console.measure(network_panel).maximum
    )
    row2_width = (
        console.measure(todos_panel).maximum + console.measure(ideas_panel).maximum
    )
    needed_width = max(row1_width, row2_width) + COLUMN_GUTTER

    if console.width >= needed_width:
        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        grid.add_row(system_panel, network_panel)
        grid.add_row(todos_panel, ideas_panel)
        console.print(grid)
    else:
        console.print(Group(system_panel, network_panel, todos_panel, ideas_panel))

    _print_sync_status(console)


def _relative_time(iso_value: str) -> str:
    when = datetime.fromisoformat(iso_value)
    seconds = (datetime.now(timezone.utc) - when).total_seconds()
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)} seconds ago"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = int(minutes // 60)
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = int(hours // 24)
    return f"{days} day{'s' if days != 1 else ''} ago"


def _print_sync_status(console: Console) -> None:
    """Show "Last synced: X ago" below the dashboard/list, only if syncing
    has been enabled via connect_to_server.sh."""
    config = sync_config.load_config()
    if not config.get("enabled") or not config.get("server_url"):
        return

    success_at = config.get("last_sync_success_at")
    if success_at:
        when_text = _relative_time(success_at)
        console.print(f"[dim]\u21bb Last synced: {when_text}[/dim]")
    else:
        console.print("[dim]\u21bb Not synced yet[/dim]")
