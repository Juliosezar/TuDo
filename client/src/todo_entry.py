"""Standalone entry point for the `todo` command (manages todos directly,
without needing the `tudo todo ...` prefix)."""

from cli import todo_app

if __name__ == "__main__":
    todo_app()
