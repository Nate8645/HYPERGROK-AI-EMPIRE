"""Market Analyst. Rule-based. Reads a supplied snapshot and does not fetch or invent one."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import MarketAnalysis
from hypergrok.clock import ensure_utc
from hypergrok.config import Settings
from hypergrok.domain import MarketSnapshot

BPS = Decimal("10000")


class MarketAnalyst:
    name = "market_analyst"
    mode = MODE

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(
        self,
        snapshot: MarketSnapshot | None,
        *,
        symbol: str,
        now: datetime,
    ) -> MarketAnalysis:
        if snapshot is None:
            return self._empty(
                symbol,
                "no market snapshot was supplied; live prices are not fabricated",
            )
        if snapshot.symbol != symbol:
            return self._empty(symbol, "snapshot symbol does not match the case", source=snapshot.source)
        if not snapshot.source.strip():
            return self._empty(symbol, "snapshot has no source label")

        observed = snapshot.observed_at()
        age = (ensure_utc(now) - observed).total_seconds()
        stale = age > self.settings.max_market_data_age_seconds or age < -2
        book_ready = all(
            value is not None
            for value in (snapshot.bid, snapshot.ask, snapshot.bid_size, snapshot.ask_size)
        )
        if not book_ready:
            return MarketAnalysis(
                status="insufficient_data",
                summary="top of book is required; a mid alone is not a trade signal",
                symbol=symbol,
                source=snapshot.source,
                fetched_at=snapshot.fetched_at,
                observed_at=observed,
                mid=snapshot.mid,
                bias="none",
                tradable=False,
                reasons=["l2_book_required"],
            )

        bid = snapshot.bid
        ask = snapshot.ask
        bid_size = snapshot.bid_size
        ask_size = snapshot.ask_size
        assert bid is not None and ask is not None and bid_size is not None and ask_size is not None
        if bid <= 0 or ask <= 0 or ask < bid:
            return self._empty(symbol, "book is crossed or non-positive", source=snapshot.source)
        size_total = bid_size + ask_size
        if size_total <= 0:
            return self._empty(symbol, "book size is zero", source=snapshot.source)

        mid = (bid + ask) / Decimal(2)
        spread_bps = (ask - bid) / mid * BPS
        imbalance = (bid_size - ask_size) / size_total
        threshold = self.settings.imbalance_threshold
        if imbalance > threshold:
            bias = "long"
        elif imbalance < -threshold:
            bias = "short"
        else:
            bias = "neutral"

        reasons: list[str] = []
        tradable = True
        if stale:
            tradable = False
            reasons.append("stale_market_data")
        if spread_bps > self.settings.wide_spread_bps:
            tradable = False
            reasons.append("wide_spread")
        if not reasons:
            reasons.append("book_ok")
        status = "stale" if stale else "completed"
        return MarketAnalysis(
            status=status,
            summary=f"{status} bias={bias} spread_bps={spread_bps} source={snapshot.source}",
            symbol=symbol,
            source=snapshot.source,
            fetched_at=snapshot.fetched_at,
            observed_at=observed,
            mid=mid,
            spread_bps=spread_bps,
            imbalance=imbalance,
            bias=bias,
            tradable=tradable,
            reasons=reasons,
        )

    @staticmethod
    def _empty(symbol: str, reason: str, source: str | None = None) -> MarketAnalysis:
        return MarketAnalysis(
            status="insufficient_data",
            summary=reason,
            symbol=symbol,
            source=source,
            bias="none",
            tradable=False,
            reasons=[reason],
        )
