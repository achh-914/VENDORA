from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import review

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Vendora",
    description="Procurement investigations done by AI agents. Decided by people.",
    version="0.1.0",
)

app.include_router(review.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vendora"}


@app.get("/review", include_in_schema=False)
def review_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "review.html")
