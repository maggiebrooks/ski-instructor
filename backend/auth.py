"""Shared API key authentication dependency."""
from fastapi import Header, HTTPException, status
from backend.config import API_KEY

async def require_api_key(x_api_key: str = Header(default="")) -> None:
    """FastAPI dependency — rejects requests without the correct X-API-Key header.
    
    If API_KEY env var is empty (local dev default), the check is skipped so
    local development works without configuration. In production, set API_KEY
    to a long random string.
    """
    if not API_KEY:
        return  # dev mode: no key configured, allow all
    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
