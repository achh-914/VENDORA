from fastapi import FastAPI

app = FastAPI(
    title="Vendora",
    description="Procurement investigations done by AI agents. Decided by people.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vendora"}
