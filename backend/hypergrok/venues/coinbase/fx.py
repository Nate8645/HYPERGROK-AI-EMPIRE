"""CHF/USD rates from an explicit config or Coinbase's public exchange-rates endpoint.

The desk never invents a rate and never stamps a missing quote as fresh.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc, utcnow
from hypergrok.config import Settings

PUBLIC_SOURCE = "coinbase_public_exchange_rates"
CONFIG_SOURCE = "explicit_config"
ALLOWED_SOURCES = {PUBLIC_SOURCE, CONFIG_SOURCE}
PUBLIC_URL = "https://api.coinbase.com/v2/exchange-rates"


class FxQuote:
    def __init__(
        self,
        *,
        base: str,
        quote: str,
        rate: Decimal,
        source: str,
        fetched_at: datetime,
    ) -> None:
        self.base = base.upper()
        self.quote = quote.upper()
        self.rate = rate
        self.source = source
        self.fetched_at = ensure_utc(fetched_at)

    def as_dict(self) -> dict:
        return {
            "base": self.base,
            "quote": self.quote,
            "rate": format(self.rate, "f"),
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat(),
        }


class FxAssessment:
    def __init__(self, ok: bool, code: str, detail: str) -> None:
        self.ok = ok
        self.code = code
        self.detail = detail


class FxUnavailable(Exception):
    pass


def quote_from_settings(settings: Settings) -> FxQuote | None:
    rate = settings.fx_usd_per_chf
    as_of = settings.fx_as_of
    if rate is None or as_of is None or rate <= 0:
        return None
    source = settings.fx_source or CONFIG_SOURCE
    if source not in ALLOWED_SOURCES:
        source = CONFIG_SOURCE
    return FxQuote(base="CHF", quote="USD", rate=rate, source=source, fetched_at=as_of)


def assess_fx(
    quote: FxQuote | None,
    *,
    now: datetime,
    max_age_seconds: float,
    base: str,
    quote_ccy: str,
) -> FxAssessment:
    if quote is None:
        return FxAssessment(False, "missing_fx_rate", "no timestamped FX quote is available")
    if quote.source not in ALLOWED_SOURCES:
        return FxAssessment(False, "missing_fx_rate", "FX source is not a documented public or explicit source")
    if quote.base != base.upper() or quote.quote != quote_ccy.upper() or quote.rate <= 0:
        return FxAssessment(False, "missing_fx_rate", "FX quote does not match the currencies being converted")
    age = (ensure_utc(now) - quote.fetched_at).total_seconds()
    if age > max_age_seconds or age < -2:
        return FxAssessment(False, "stale_fx_rate", f"fx age {age:.3f}s exceeds {max_age_seconds}s")
    return FxAssessment(True, "ok", f"fx age {age:.3f}s from {quote.source}")


def parse_public_exchange_rates(payload: object, *, base: str, quote: str, fetched_at: datetime) -> FxQuote:
    if not isinstance(payload, dict):
        raise FxUnavailable("public exchange-rates payload is not an object")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        raise FxUnavailable("public exchange-rates payload has no data")
    rates = data.get("rates")
    if not isinstance(rates, dict) or quote.upper() not in rates:
        raise FxUnavailable(f"public exchange-rates payload has no {quote.upper()} rate")
    try:
        rate = Decimal(str(rates[quote.upper()]))
    except Exception as exc:
        raise FxUnavailable("public exchange rate is not a decimal") from exc
    if rate <= 0:
        raise FxUnavailable("public exchange rate is not positive")
    return FxQuote(
        base=base.upper(),
        quote=quote.upper(),
        rate=rate,
        source=PUBLIC_SOURCE,
        fetched_at=ensure_utc(fetched_at),
    )


class PublicExchangeRateClient:
    """GET https://api.coinbase.com/v2/exchange-rates. No API key."""

    def __init__(
        self,
        transport,
        *,
        clock: Callable[[], datetime] | None = None,
        base_url: str = PUBLIC_URL,
    ) -> None:
        self.transport = transport
        self.clock = clock or utcnow
        self.base_url = base_url

    def usd_per(self, currency: str) -> FxQuote:
        status, text = self.transport.get(f"{self.base_url}?currency={currency.upper()}", timeout=10)
        fetched_at = self.clock()
        if status != 200:
            raise FxUnavailable(f"public exchange-rates HTTP {status}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise FxUnavailable("public exchange-rates returned non-JSON") from exc
        return parse_public_exchange_rates(payload, base=currency, quote="USD", fetched_at=fetched_at)
