"""Customer API keys. Each key belongs to one tenant (one customer).

Set VENDORA_API_KEYS="key-for-acme:acme,key-for-nordic:nordic". Every request
to the cases API must then send the header X-API-Key. A key opens only its own
tenant, so one customer can never read another customer's cases.

Leave VENDORA_API_KEYS empty for single-customer use (no key needed), which is
how the demo and the tests run.
"""

import hmac
import os
import re

from fastapi import Header, HTTPException

from app.store import DEFAULT_TENANT

TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def load_keys() -> dict[str, str]:
    """Read the key -> tenant table from the environment."""
    keys: dict[str, str] = {}
    for part in (os.getenv("VENDORA_API_KEYS") or "").split(","):
        part = part.strip()
        if not part:
            continue
        key, _, tenant = part.partition(":")
        key, tenant = key.strip(), tenant.strip().lower()
        if not key or not TENANT_RE.match(tenant):
            msg = f"Bad VENDORA_API_KEYS entry for tenant {tenant!r}"
            raise ValueError(msg)
        keys[key] = tenant
    return keys


def tenant_for(key: str | None, keys: dict[str, str]) -> str | None:
    """Return the tenant that owns this key, or None. Compares in constant time."""
    found = None
    for known, tenant in keys.items():
        if key is not None and hmac.compare_digest(known.encode(), key.encode()):
            found = tenant
    return found


def current_tenant(x_api_key: str | None = Header(default=None)) -> str:
    keys = load_keys()
    if not keys:
        return DEFAULT_TENANT
    tenant = tenant_for(x_api_key, keys)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    return tenant
