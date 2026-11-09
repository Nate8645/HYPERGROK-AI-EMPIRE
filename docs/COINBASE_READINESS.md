# Coinbase readiness

Updated 2026-11-09. This is a technical status. It is not permission to send a live order.

## What was read

A read-only Coinbase connection returned these facts during this session. The book timestamp is `2026-11-09T20:37:29.751052Z` (21:37 Europe/Zurich). Account identifiers from that read are not stored.

- Default-portfolio trading balance: **10.896768 USDC** available, hold 0.
- BTC, CHF, and EUR were returned with available 0. No USD account was in the response. Available crypto quantity was 0.
- The fee endpoint also reported a rounded `total_balance` of `10.90`. Trading math uses the available balance `10.896768`, not that rounded figure.
- Fee tier **Intro**: maker `0.0009`, taker `0.001`.
- `BTC-USDC`, `ETH-USDC`, and `SOL-USDC` were online. Each had `quote_min_size` 1, `base_increment` 0.00000001, `quote_increment` 0.01, and `base_min_size` 0.00000001.
- The top five `BTC-USDC` book levels from that same read are in `backend/tests/fixtures/coinbase_read_2026-11-09.json`.

That file is a test fixture. The desk does not treat it as the live balance. `funded_quote_currency` returns `USDC` when USDC is the only positive quote balance, which is why orders for this account use the USDC pairs.

No live order was sent. No live order preview was sent. The repository process has no CDP key, so its own adapter was not the client for this read.

## BUY

Implemented on `coinbase-advanced-py==1.8.4` for spot market and limit (optional post-only).

Path: labelled market data, Risk Manager, read-only preview, execution gate, user approval token, submit, `get_order` confirmation, journal. A missing `client_order_id` is rejected. Reuse of an id is a duplicate. An unknown result is reconciled with list/get and is not sent again.

Technically this works against a mock. It does not work against the live account until the gates below are set.

## SELL

Same order types. A sell with no base balance is `no_position`. A sell larger than the available base is `sell_exceeds_holdings`. Fees stay in the average-cost P&L.

Technically this works against a mock. The read showed no crypto to sell.

## Seven agents

`POST /api/desk/team` runs Desk Lead, Market Analyst, Research Analyst, Strategist, Risk Manager, Execution Trader, and Trade Reviewer as one case. They are rule-based. If the Risk Manager passes and a Coinbase client is configured, the case also calls the preview endpoint. Submit stays false unless the live flags are on and that order has an unused approval token. The flags default to false.

## Risk engine

Every submit calls the Risk Manager. The broker rejects an id that did not pass. The capital-utilization view uses the same 1% equity rule, with the configured fee and slippage floors. On the 2026-11-09 USDC snapshot, a 1% stop makes 100% utilization fail that rule. 10% utilization passes it in the fixture test. There is no saved backtest for the USDC pairs, so the panel says `Keine Daten` rather than reuse the USD-pair run.

## Dashboard

`frontend/` is the local iPhone desk: cash, portfolio, public tickers, journal signals, agent status, fees, P&L, risk, utilization, open orders, fills, and a per-order approval form. Missing API data renders `Keine Daten`.

`monitor/` is the public page. It does not show this balance, an approval form, or a trade button. GitHub Pages is not enabled.

## 100% capital simulation

This does not replace the 1% loss rule. Leverage stays 1, borrowing stays 0, and one position remains the maximum.

On 10.896768 USDC, with the Intro taker rate of 0.001 on entry and on exit, the order is `floor((balance - fee reserve) to 0.01)` = **10.87 USDC**. Entry fee 0.01087, exit fee 0.01087, fee reserve 0.02174, remainder 0.005028. A size of 10.88 plus both fees does not fit.

The required stop that keeps the loss, after both fees, the saved book spread, and 10 bps of slippage on each side, inside 1% of 10.896768 is a price distance of **0.6024%**. Loss at that stop is 0.10896768 USDC, the 1% budget. One-minute noise on the sample was 0.0439% and ATR was 0.0542%, so the required stop is wider than that noise. The stop is not rejected for being tighter than ATR.

It is rejected because historical gaps would break the 1% budget too often. Sample fetched 2026-11-09 from `api.exchange.coinbase.com` with a browser user agent:

- BTC-USD 1-minute bars: 2750, 2026-11-07 22:58Z through 2026-11-09 20:47Z. Share of bars whose open-to-low or previous-close-to-low move would push the loss through 1%: **0.036%**.
- BTC-USD daily bars: 350, 2025-11-25 through 2026-11-09. Share of sessions whose low versus the previous close would push the loss through 1%: **71.3%**.

A material share, for this check, means 5% or more. 71.3% is above that, so the Risk Manager simulation status is **REJECT** (`overshoot_breaches_risk`). That result was not stored as permission to send.

Loss scenarios on the 10.87 size:

- At the stop: 0.10896768 USDC
- At a typical daily overshoot (about 1.20% past the stop): 0.2399 USDC
- At the worst daily adverse move in the sample (14.82%): 1.654 USDC
- Total loss of the position, size plus the entry fee: 10.88087 USDC

BTC-USDC one-minute history was not usable: an explicit window returned an empty array, and the undated response was from 2022-07-13. SOL-USDC one-minute returned HTTP 404. The percentages above are from BTC-USD. The balance is the USDC snapshot. No live preview was sent (`Keine Daten`).

Out-of-sample daily comparison on the same BTC-USD file, last 70 bars, 2026-09-01 through 2026-11-09, stop distance 5%, same fee and slippage rates: the 25%, 50%, and 100% variants were rejected by the 1% rule and have no trades. The 10% and the 1%-risk variants did trade. Expectancy was negative for ema_cross, breakout, and momentum. Mean reversion was about +0.00065 per trade on 3 trades. Every sample is too small to be a forecast. Exit rules are signal flat, stop, take-profit, time stop, and end of sample.

## Still blocked for real money

- `LIVE_TRADING_ENABLED` and `COINBASE_LIVE_ENABLED` are false.
- The product allowlist is empty and the capital cap is 0.
- No CDP key is in this repository. A live key must be View and Trade only, stored outside the repo.
- The transfer-permission check is tested with a mock. It was not called on the live key.
- The API has no authentication.
- There is no crypto position to sell.
- Phase 3 backtests are for USD pairs, 2025-11-25 through 2026-11-09, and every strategy is `too_few_trades`. They are not a forecast.
