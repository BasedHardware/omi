"""FastAPI helpers for Omi plugin apps."""

from fastapi import FastAPI


def create_app(title: str, description: str, version: str = "1.0.0") -> FastAPI:
    """Create a FastAPI app with the common metadata fields."""
    return FastAPI(title=title, description=description, version=version)
