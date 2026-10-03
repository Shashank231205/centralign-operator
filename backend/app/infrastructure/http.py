"""Shared outbound HTTP client.

TLS is verified against the operating system trust store (not a bundled CA file), so corporate
proxies and endpoint-security products that install their own root CA work without ever
turning verification off.
"""

import ssl

import httpx
import truststore

_MAX_CONNECTIONS = 50
_MAX_KEEPALIVE = 20


def create_http_client() -> httpx.AsyncClient:
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    return httpx.AsyncClient(
        verify=context,
        limits=httpx.Limits(
            max_connections=_MAX_CONNECTIONS, max_keepalive_connections=_MAX_KEEPALIVE
        ),
        follow_redirects=False,
    )
