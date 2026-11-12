import os

# Tests always use the in-memory store, never the real database.
os.environ.pop("VENDORA_DB", None)
