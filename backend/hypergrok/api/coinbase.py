"""Coinbase read and spot-order routes. Responses are allow-listed and redacted."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from hypergrok.clock import utcnow
from hypergrok.logging_config import redact
from hypergrok.money import Dec
from hypergrok.serialize import to_jsonable
from hypergrok.venues.coinbase.market import CoinbaseFailure

router = APIRouter(prefix="/api/coinbase")


class PreviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str
    side: str
    order_type: str = "market"
    quote_size: Dec | None = None
    base_size: Dec | None = None
    limit_price: Dec | None = None
    post_only: bool = False
    client_order_id: str = "preview"


class OrderBody(PreviewBody):
    client_order_id: str = Field(min_length=1, max_length=128)
    request_live: bool = False
    approval_token: str | None = None
    entry_price: Dec | None = None
    stop_price: Dec | None = None
    market_data_time: datetime | None = None
    fee_bps_round_trip: Dec | None = None
    slippage_bps_round_trip: Dec | None = None


def _public(payload: object) -> dict:
    return redact(to_jsonable(payload))


def _failure(exc: CoinbaseFailure) -> JSONResponse:
    status = 409 if exc.code == "coinbase_not_configured" else 400
    if exc.code in {"invalid_api_key", "missing_api_permissions"}:
        status = 403 if exc.code == "missing_api_permissions" else 401
    return JSONResponse(status_code=status, content={"error": {"code": exc.code, "message": exc.message}})


@router.get("/status")
def status(request: Request) -> dict:
    return _public(request.app.state.coinbase.status())


@router.get("/markets")
def markets(request: Request):
    try:
        return _public(request.app.state.coinbase.list_products())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/markets/{product_id}")
def market(product_id: str, request: Request):
    try:
        return _public(request.app.state.coinbase.get_product(product_id))
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/markets/{product_id}/book")
def book(product_id: str, request: Request):
    try:
        return _public(request.app.state.coinbase.best_bid_ask(product_id))
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/markets/{product_id}/candles")
def candles(
    product_id: str,
    request: Request,
    start: str = Query(...),
    end: str = Query(...),
    granularity: str = Query("ONE_MINUTE"),
):
    try:
        return _public(request.app.state.coinbase.candles(product_id, start=start, end=end, granularity=granularity))
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/balances")
def balances(request: Request):
    try:
        return _public(request.app.state.coinbase.balances())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/portfolios")
def portfolios(request: Request):
    try:
        return _public(request.app.state.coinbase.portfolios())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/fees")
def fees(request: Request):
    try:
        return _public(request.app.state.coinbase.fees())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/fx")
def fx(request: Request, source: str = Query("config")):
    service = request.app.state.coinbase
    try:
        quote = service.fx_quote(refresh_public=source == "coinbase_public")
    except Exception:
        quote = None
    if quote is None:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "missing_fx_rate", "message": "no timestamped FX quote is available"}},
        )
    return _public(quote.as_dict())


@router.get("/portfolio")
def portfolio(request: Request):
    try:
        return _public(request.app.state.coinbase.portfolio())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.post("/orders/preview")
def preview(body: PreviewBody, request: Request):
    try:
        return _public(request.app.state.coinbase.preview_order(body.model_dump(mode="json")))
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.post("/orders")
def place(body: OrderBody, request: Request):
    payload = body.model_dump(mode="json")
    payload["market_data_time"] = body.market_data_time or utcnow()
    try:
        return _public(request.app.state.coinbase.submit_order(payload))
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/orders")
def orders(request: Request):
    try:
        return _public(request.app.state.coinbase.list_orders())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.get("/fills")
def fills(request: Request):
    try:
        return _public(request.app.state.coinbase.list_fills())
    except CoinbaseFailure as exc:
        return _failure(exc)


@router.post("/orders/cancel-open")
def cancel_open(request: Request):
    return _public(request.app.state.coinbase.cancel_open_if_armed())
