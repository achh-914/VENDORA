"""App entry point with the review dashboard mounted.

Run:  uvicorn app.server:app --reload
Then open http://127.0.0.1:8000/review
"""

from app.main import app
from app.review import router

app.include_router(router)
