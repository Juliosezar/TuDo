"""Standalone entry point for the `idea` command (manages ideas directly,
without needing the `tudo idea ...` prefix)."""

from cli import idea_app

if __name__ == "__main__":
    idea_app()
