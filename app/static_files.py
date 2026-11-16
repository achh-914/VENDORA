"""Serve the static HTML pages."""

from pathlib import Path

from fastapi.responses import HTMLResponse

STATIC_DIR = Path(__file__).parent / "static"


def page(name: str) -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / name).read_text(encoding="utf-8"))
