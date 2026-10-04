"""API key handling. Keys are stored only as SHA-256 hashes; plaintext never touches the DB."""

import hashlib

API_KEY_HEADER = "X-API-Key"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()
