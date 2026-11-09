"""Build the official Advanced Trade client. Import happens only when a key exists."""

from __future__ import annotations

from hypergrok.venues.coinbase.credentials import CoinbaseCredentials

SDK_VERSION = "1.8.4"


def build_rest_client(credentials: CoinbaseCredentials, timeout: int = 10):
    """Pass the CDP key into coinbase-advanced-py. verbose stays off so the SDK does not debug-log it."""

    from coinbase.rest import RESTClient

    return RESTClient(
        api_key=credentials.key_name,
        api_secret=credentials.private_key,
        verbose=False,
        timeout=timeout,
    )
