"""Server configuration, sourced from environment variables."""

import os
from pathlib import Path

# If set, every request (except /api/health) must include
# "Authorization: Bearer <API_KEY>". If unset, the API is open (fine for a
# strictly localhost-bound deployment, not recommended if exposed publicly).
API_KEY = os.environ.get("TUDO_API_KEY") or None

DB_PATH = Path(os.environ.get("TUDO_DB_PATH", "/data/tudo.db"))

DEFAULT_HISTORY_DAYS = 7
