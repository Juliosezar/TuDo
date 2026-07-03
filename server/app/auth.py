"""Simple bearer-token auth, enforced only when TUDO_API_KEY is configured."""

from fastapi import Header, HTTPException, status

from . import config


async def require_api_key(authorization: str | None = Header(default=None)) -> None:
    if config.API_KEY is None:
        return  # No key configured: API is open (fine for a localhost-only deployment).

    expected = f"Bearer {config.API_KEY}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
