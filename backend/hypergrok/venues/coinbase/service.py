"""Facade used by REST, the kill switch, and the execution trader."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from hypergrok.clock import utcnow
from hypergrok.config import Settings
from hypergrok.execution.adapter import ExecutionAdapter
from hypergrok.execution.gate import ExecutionGate
from hypergrok.risk.service import RiskService
from hypergrok.store import DeskStore
from hypergrok.venues.coinbase.adapter import CoinbaseExecutionAdapter
from hypergrok.venues.coinbase.broker import CoinbaseBroker
from hypergrok.venues.coinbase.credentials import load_credentials
from hypergrok.venues.coinbase.fx import assess_fx, quote_from_settings
from hypergrok.venues.coinbase.market import (
    SOURCE,
    CoinbaseFailure,
    as_dict,
    classify_exception,
    fee_bps_from_summary,
    parse_balances,
    parse_best_bid_ask,
    parse_candles,
    parse_portfolios,
    parse_book_levels,
    parse_product,
    prepare_order_sizes,
    public_fill,
    public_order,
    snapshot_from_book,
)
from hypergrok.venues.coinbase.permissions import assess_key_permissions
from hypergrok.venues.coinbase.pnl import compute_portfolio
from hypergrok.venues.coinbase.utilization import backtest_for_product, funded_quote_currency, utilization_variants
from hypergrok.venues.coinbase.sdk import SDK_VERSION, build_rest_client
from hypergrok.domain import OrderIntent


class CoinbaseService:
    def __init__(
        self,
        settings: Settings,
        *,
        risk_service: RiskService | None = None,
        gate: ExecutionGate | None = None,
        dry_run: ExecutionAdapter | None = None,
        store: DeskStore | None = None,
        client=None,
        client_factory=build_rest_client,
        public_client=None,
        clock=utcnow,
    ) -> None:
        self.settings = settings
        self.risk_service = risk_service
        self.gate = gate
        self.dry_run = dry_run
        self.store = store
        self._client = client
        self._factory = client_factory
        self.public_client = public_client
        self.clock = clock
        self._broker: CoinbaseBroker | None = None
        self._permission_block: str | None = None

    @property
    def broker(self) -> CoinbaseBroker:
        if self._broker is None:
            self._broker = CoinbaseBroker(self._require_client(), clock=self.clock, store=self.store)
        return self._broker

    def adapter(self) -> CoinbaseExecutionAdapter:
        return CoinbaseExecutionAdapter(self.broker)

    def configured(self) -> bool:
        return self._client is not None or load_credentials(self.settings) is not None

    def live_armed(self) -> bool:
        if self._permission_block:
            return False
        return bool(
            self.settings.live_trading_enabled
            and self.settings.coinbase_live_enabled
            and self.configured()
            and self.settings.coinbase_products()
            and self.settings.coinbase_max_capital > 0
        )

    def check_key_permissions(self) -> dict:
        """Optional read of GET /api/v3/brokerage/key_permissions. A transfer-capable key cannot arm."""
        try:
            raw = self._call(lambda client: client.get_api_key_permissions())
        except CoinbaseFailure as exc:
            self._permission_block = exc.code
            return {
                "can_view": None,
                "can_trade": None,
                "can_transfer": None,
                "arming_allowed": False,
                "reason": exc.code,
            }
        assessed = assess_key_permissions(raw)
        self._permission_block = None if assessed["arming_allowed"] else assessed["reason"]
        return assessed

    def status(self) -> dict:
        products = sorted(self.settings.coinbase_products())
        prerequisites = [
            {"id": "credentials", "ok": self.configured(), "detail": "CDP API key is configured" if self.configured() else "CDP API key is not configured"},
            {"id": "live_trading_enabled", "ok": self.settings.live_trading_enabled, "detail": "LIVE_TRADING_ENABLED"},
            {"id": "coinbase_live_enabled", "ok": self.settings.coinbase_live_enabled, "detail": "COINBASE_LIVE_ENABLED"},
            {"id": "product_allowlist", "ok": bool(products), "detail": "allowlist is empty" if not products else "allowlist is set"},
            {"id": "max_capital", "ok": self.settings.coinbase_max_capital > 0, "detail": "max capital is 0" if self.settings.coinbase_max_capital <= 0 else "max capital is set"},
            {"id": "human_approval", "ok": False, "detail": "every live order still needs its own stored approval token"},
        ]
        return {
            "configured": self.configured(),
            "live_enabled": self.settings.coinbase_live_enabled,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "live_armed": self.live_armed(),
            "product_allowlist": products,
            "max_capital": format(self.settings.coinbase_max_capital, "f"),
            "max_capital_currency": self.settings.coinbase_max_capital_currency or self.settings.account_currency,
            "prerequisites": prerequisites,
            "spot_only": True,
            "transfers_enabled": False,
            "withdrawals_enabled": False,
            "conversions_enabled": False,
            "sdk": f"coinbase-advanced-py=={SDK_VERSION}",
            "implementation": "rule_based",
            "key_permission_block": self._permission_block,
        }

    def list_products(self) -> dict:
        raw = self._call(lambda client: client.get_products(product_type="SPOT", get_all_products=True))
        rows = as_dict(raw).get("products") or []
        products = []
        for row in rows:
            try:
                products.append(parse_product(row))
            except CoinbaseFailure:
                continue
        return {"source": SOURCE, "fetched_at": self.clock().isoformat(), "products": products}

    def get_product(self, product_id: str) -> dict:
        raw = self._call(lambda client: client.get_product(product_id))
        product = parse_product(raw)
        product["fetched_at"] = self.clock().isoformat()
        return product

    def best_bid_ask(self, product_id: str) -> dict:
        raw = self._call(lambda client: client.get_best_bid_ask([product_id]))
        return {"source": SOURCE, "books": parse_best_bid_ask(raw, fetched_at=self.clock())}

    def safe_snapshot(self, symbol: str):
        try:
            raw = self._call(lambda client: client.get_product_book(symbol))
            return snapshot_from_book(raw, symbol=symbol, fetched_at=self.clock())
        except Exception:
            return None

    def order_book(self, product_id: str) -> dict:
        raw = self._call(lambda client: client.get_product_book(product_id))
        snapshot = snapshot_from_book(raw, symbol=product_id, fetched_at=self.clock())
        return snapshot.model_dump(mode="json")

    def candles(self, product_id: str, *, start: str, end: str, granularity: str) -> dict:
        raw = self._call(lambda client: client.get_candles(product_id, start, end, granularity))
        return parse_candles(raw, fetched_at=self.clock(), product_id=product_id)

    def balances(self) -> dict:
        raw = self._call(lambda client: client.get_accounts())
        parsed = parse_balances(raw)
        parsed["fetched_at"] = self.clock().isoformat()
        return parsed

    def portfolios(self) -> dict:
        raw = self._call(lambda client: client.get_portfolios())
        return {"source": SOURCE, "fetched_at": self.clock().isoformat(), "portfolios": parse_portfolios(raw)}

    def fees(self) -> dict:
        raw = self._call(lambda client: client.get_transaction_summary(product_type="SPOT"))
        summary = fee_bps_from_summary(raw, order_type="market", post_only=False)
        summary["fetched_at"] = self.clock().isoformat()
        return summary

    def fx_quote(self, *, refresh_public: bool = False):
        configured = quote_from_settings(self.settings)
        if configured is not None and not refresh_public:
            return configured
        if refresh_public and self.public_client is not None:
            return self.public_client.usd_per("CHF")
        return configured

    def preview_order(self, order: dict) -> dict:
        product = self.get_product(str(order["product_id"]))
        prepared = prepare_order_sizes(product, order)
        mapped = self.broker.preview(prepared)
        self._journal("preview", f"preview {prepared['product_id']}", {"preview": mapped, "order": prepared}, symbol=prepared["product_id"])
        return mapped

    def portfolio(self) -> dict:
        orders = self.broker.historical_orders()
        fills = []
        for order in orders:
            if order.get("order_id"):
                fills.extend(self.broker.fills_for(order.get("client_order_id") or "", order.get("order_id")))
        marks = {}
        for product_id in {fill.get("product_id") for fill in fills if fill.get("product_id")}:
            try:
                books = self.best_bid_ask(str(product_id))["books"]
            except CoinbaseFailure:
                books = []
            if books and books[0].get("best_bid") and books[0].get("best_ask"):
                bid = Decimal(str(books[0]["best_bid"]))
                ask = Decimal(str(books[0]["best_ask"]))
                marks[str(product_id)] = {
                    "price": (bid + ask) / Decimal(2),
                    "source": SOURCE,
                    "fetched_at": books[0].get("fetched_at"),
                }
        report = compute_portfolio(fills, marks)
        report["source"] = SOURCE
        report["fetched_at"] = self.clock().isoformat()
        return report

    def submit_order(self, order: dict, *, now: datetime | None = None) -> dict:
        moment = now or self.clock()
        if self.risk_service is None or self.gate is None or self.dry_run is None:
            raise CoinbaseFailure("desk_not_ready", "risk engine or execution gate is not wired")
        product = None
        prepared = dict(order)
        fee_bps = order.get("fee_bps_round_trip")
        slip_bps = order.get("slippage_bps_round_trip")
        if self.configured():
            try:
                product = self.get_product(str(order["product_id"]))
                prepared = {**order, **prepare_order_sizes(product, order)}
                summary = self.fees()
                fee_bps = summary["fee_bps_round_trip"]
            except CoinbaseFailure as exc:
                self._journal("order_rejected", exc.message, {"code": exc.code}, symbol=str(order.get("product_id") or "-"))
                raise
        intent = self._intent(prepared, product, fee_bps, slip_bps, moment)
        from hypergrok.agents.risk_manager import RiskManager

        decision = RiskManager(self.risk_service).run(intent, now=moment, case_id=uuid.uuid4().hex)
        if decision.status != "PASS":
            self._journal("risk_rejected", decision.summary, {"reasons": decision.reasons}, symbol=intent.symbol)
            return {"status": "rejected", "reason": "risk_rejected", "decision": decision.model_dump(mode="json"), "transmitted": False, "stages": ["risk_manager"]}
        balance_block = self._balance_block(prepared, product)
        if balance_block is not None:
            self._journal(balance_block, balance_block, {"product_id": intent.symbol}, symbol=intent.symbol)
            return {"status": "rejected", "reason": balance_block, "decision": decision.model_dump(mode="json"), "transmitted": False, "stages": ["risk_manager", "balance"]}
        preview = None
        if self.configured():
            try:
                preview = self.broker.preview(prepared)
            except CoinbaseFailure as exc:
                self._journal("preview_rejected", exc.message, {"code": exc.code}, symbol=intent.symbol)
                raise
            self._journal("preview", f"preview {intent.symbol}", preview, symbol=intent.symbol)
        fx = self.fx_quote()
        from hypergrok.order_binding import fingerprint

        gate = self.gate.authorize(
            mode="live" if order.get("request_live") else "dry_run",
            client_order_id=intent.client_order_id,
            approval_token=order.get("approval_token"),
            order_hash=fingerprint(order),
            venue="coinbase",
            product_id=intent.symbol,
            notional=intent.notional,
            notional_currency=intent.notional_currency,
            fx_quote=fx,
        )
        if not gate.allowed:
            self._journal("execution_rejected", gate.reason, {"reason": gate.reason}, symbol=intent.symbol)
            return {
                "status": "rejected",
                "reason": gate.reason,
                "decision": decision.model_dump(mode="json"),
                "transmitted": False,
                "preview": preview,
                "stages": ["risk_manager", "preview", "approval"],
            }
        if gate.reason != "coinbase_live":
            recorded = self.dry_run.execute({"venue": "coinbase", **prepared, "notional": format(intent.notional, "f")})
            self._journal("dry_run_recorded", "dry run only", recorded.payload, symbol=intent.symbol)
            return {
                "status": "recorded",
                "transmitted": False,
                "payload": recorded.payload,
                "decision": decision.model_dump(mode="json"),
                "preview": preview,
                "stages": ["risk_manager", "preview", "journal"],
            }
        permissions = self.check_key_permissions()
        if not permissions["arming_allowed"]:
            self._journal("key_permission_blocked", permissions["reason"], permissions, symbol=intent.symbol)
            return {
                "status": "rejected",
                "reason": permissions["reason"],
                "decision": decision.model_dump(mode="json"),
                "transmitted": False,
                "preview": preview,
            }
        if self.store is not None and order.get("approval_token"):
            self.store.mark_approval_used(order["approval_token"], moment)
        result = self.broker.submit(prepared)
        transmitted = str(result.get("status") or "").lower() in {"open", "filled", "pending", "submitted", "queued"}
        self._journal(
            "order_submitted" if transmitted else str(result.get("reason") or "order_rejected"),
            f"order {intent.client_order_id} {result.get('status')}",
            result,
            symbol=intent.symbol,
        )
        for fill in result.get("fills") or []:
            self._journal("fill", f"fill {fill.get('trade_id') or fill.get('entry_id')}", fill, symbol=intent.symbol)
        if result.get("confirmation"):
            self._journal("order_confirmed", f"confirmed {intent.client_order_id}", result["confirmation"], symbol=intent.symbol)
        return {
            "status": result.get("status"),
            "transmitted": transmitted,
            "result": result,
            "decision": decision.model_dump(mode="json"),
            "preview": preview,
            "stages": ["market_data", "risk_manager", "preview", "approval", "submit", "confirm", "journal"],
        }

    def _available(self, currency: str | None) -> Decimal:
        held = self.balances()
        total = Decimal("0")
        for row in held["accounts"]:
            if currency is None or row.get("currency") == currency:
                total += Decimal(str(row.get("available") or "0"))
        return total

    def _balance_block(self, prepared: dict, product: dict | None) -> str | None:
        if not self.configured() or product is None:
            return None
        side = str(prepared.get("side") or "")
        if side == "buy":
            available = self._available(product.get("quote_currency"))
            need = Decimal(str(prepared.get("quote_size") or "0"))
            if need <= 0 and prepared.get("base_size") and (prepared.get("limit_price") or prepared.get("entry_price")):
                price = Decimal(str(prepared.get("limit_price") or prepared.get("entry_price")))
                need = Decimal(str(prepared["base_size"])) * price
            if available <= 0:
                return "empty_account"
            if need > available:
                return "insufficient_balance"
            return None
        if side == "sell":
            available = self._available(product.get("base_currency"))
            need = Decimal(str(prepared.get("base_size") or "0"))
            if available <= 0:
                return "no_position"
            if need > available:
                return "sell_exceeds_holdings"
        return None

    def book_levels(self, product_id: str) -> dict:
        raw = self._call(lambda client: client.get_product_book(product_id))
        return parse_book_levels(raw)

    def capital_utilization(self, *, product_id: str, side: str, stop_fraction: Decimal, post_only: bool = False) -> dict:
        if not self.configured():
            return {"available": False, "reason": "coinbase_not_configured", "backtest": "Keine Daten", "variants": []}
        balances = self.balances()
        quote = funded_quote_currency(balances["accounts"])
        product = self.get_product(product_id)
        if quote is None or product.get("quote_currency") != quote:
            return {
                "available": False,
                "reason": "quote_not_funded",
                "quote_currency": quote,
                "backtest": "Keine Daten",
                "variants": [],
            }
        tradable = self._available(quote)
        fees = self.fees()
        book = self.book_levels(product_id)
        summary = self._saved_backtests()
        report = utilization_variants(
            tradable=tradable,
            quote_currency=quote,
            taker_fee_rate=Decimal(fees["taker_fee_rate"]),
            maker_fee_rate=Decimal(fees["maker_fee_rate"]),
            quote_increment=Decimal(str(product["quote_increment"])),
            quote_min_size=Decimal(str(product["quote_min_size"])),
            stop_fraction=stop_fraction,
            equity=tradable,
            max_risk_fraction=self.settings.max_planned_risk_fraction,
            bids=book.get("bids") or [],
            asks=book.get("asks") or [],
            side=side,
            post_only=post_only,
            backtest=backtest_for_product(summary, product_id),
            fee_floor_rate=self.settings.default_fee_bps_round_trip / Decimal("10000"),
            slippage_floor_rate=self.settings.default_slippage_bps_round_trip / Decimal("10000"),
        )
        report["available"] = True
        report["source"] = SOURCE
        report["fetched_at"] = self.clock().isoformat()
        report["product_id"] = product_id
        report["book_time"] = book.get("time")
        return report

    def public_tickers(self, products: list[str], transport=None) -> dict:
        rows = []
        for product_id in products:
            rows.append(_public_ticker(product_id, transport))
        return {"source": "coinbase_exchange_public", "tickers": rows}

    def _saved_backtests(self) -> dict | None:
        from pathlib import Path

        path = Path(__file__).resolve().parents[4] / "docs" / "research" / "backtests" / "public-candles.json"
        if not path.exists():
            return None
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    def list_orders(self) -> dict:
        return {"orders": [public_order(item) for item in self.broker.historical_orders()]}

    def list_fills(self) -> dict:
        raw = self._call(lambda client: client.get_fills())
        fills = [public_fill(item) for item in (as_dict(raw).get("fills") or [])]
        return {"source": SOURCE, "fills": fills}

    def cancel_open_if_armed(self) -> dict:
        if not (self.settings.live_trading_enabled and self.settings.coinbase_live_enabled and self.configured()):
            return {"attempted": False, "cancelled": [], "reason": "coinbase_live_not_armed"}
        try:
            result = self.broker.cancel_open()
        except Exception as exc:
            code = classify_exception(exc)
            return {"attempted": True, "cancelled": [], "reason": code}
        self._journal("cancel", "cancelled open Coinbase spot orders", result, symbol="-")
        return {"attempted": True, **result}

    def _intent(self, prepared: dict, product: dict | None, fee_bps, slip_bps, now: datetime) -> OrderIntent:
        quote = Decimal(str(prepared.get("quote_size") or prepared.get("notional") or "0"))
        price = prepared.get("entry_price") or prepared.get("limit_price")
        if quote <= 0 and prepared.get("base_size") and price:
            quote = Decimal(str(prepared["base_size"])) * Decimal(str(price))
        currency = self.settings.account_currency
        if product and product.get("quote_currency"):
            currency = str(product["quote_currency"]).upper()
        entry = Decimal(str(prepared.get("entry_price") or prepared.get("limit_price") or "100"))
        stop = prepared.get("stop_price")
        fx = self.fx_quote()
        return OrderIntent(
            client_order_id=str(prepared.get("client_order_id")),
            venue="coinbase",
            symbol=str(prepared.get("product_id") or prepared.get("symbol")),
            side=str(prepared.get("side")),
            notional=quote,
            notional_currency=currency,
            leverage=Decimal("1"),
            entry_price=entry,
            stop_price=None if stop in (None, "") else Decimal(str(stop)),
            market_data_time=prepared.get("market_data_time") or now,
            fee_bps_round_trip=None if fee_bps in (None, "") else Decimal(str(fee_bps)),
            slippage_bps_round_trip=None if slip_bps in (None, "") else Decimal(str(slip_bps)),
            usd_per_notional_currency=None if fx is None else fx.rate,
            fx_source=None if fx is None else fx.source,
            fx_as_of=None if fx is None else fx.fetched_at,
        )

    def _require_client(self):
        if self._client is not None:
            return self._client
        credentials = load_credentials(self.settings)
        if credentials is None:
            raise CoinbaseFailure("coinbase_not_configured", "Coinbase credentials are not configured")
        self._client = self._factory(credentials)
        return self._client

    def _call(self, fn):
        try:
            return fn(self._require_client())
        except CoinbaseFailure:
            raise
        except Exception as exc:
            raise CoinbaseFailure(classify_exception(exc), "Coinbase request failed") from exc

    def _journal(self, outcome: str, summary: str, payload: dict, *, symbol: str) -> None:
        if self.store is None:
            return
        self.store.add_journal(
            case_id=outcome,
            symbol=symbol,
            venue="coinbase",
            outcome=outcome,
            summary=summary,
            payload=payload,
            now=self.clock(),
        )


def _public_ticker(product_id: str, transport) -> dict:
    url = f"https://api.exchange.coinbase.com/products/{product_id}/ticker"
    try:
        if transport is None:
            import httpx

            response = httpx.get(url, timeout=10)
            status, text = response.status_code, response.text
        else:
            status, text = transport.get(url, 10)
        if status != 200:
            return {"product_id": product_id, "price": None, "detail": "Keine Daten"}
        import json

        body = json.loads(text)
        price = body.get("price")
        if price in (None, ""):
            return {"product_id": product_id, "price": None, "detail": "Keine Daten"}
        return {"product_id": product_id, "price": str(price), "time": body.get("time"), "bid": body.get("bid"), "ask": body.get("ask")}
    except Exception:
        return {"product_id": product_id, "price": None, "detail": "Keine Daten"}
