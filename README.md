# HYPERGROK AI EMPIRE

Phase 1 plus a Coinbase spot adapter. Hyperliquid order routing, Solana, wallet signing, and a hosted dashboard login are still absent. The backend is a rule-based FastAPI desk. By default it does not send orders.

Coinbase Advanced Trade can send a spot order only when every live prerequisite below is set. Authentication is the official `coinbase-advanced-py` SDK JWT for the REST API. That is not a blockchain signature and the desk does not hold a wallet seed.

## Current status

Implemented in this phase:

- FastAPI app with `GET /health`, `WS /ws/events`, and REST for agent status, risk config, the paper account, kill switch, risk evaluation, the journal, human approval tokens, and a desk run.
- Risk engine that returns structured `PASS` / `REJECT` decisions. Agents cannot bypass it by choosing a larger size.
- Execution gate and a `DryRunAdapter` that records the payload that would have been sent.
- Seven rule-based agents and an orchestrator. No language-model calls and no paid APIs.
- Public Hyperliquid `info` client for `allMids`, `l2Book`, and `meta`, labelled with source and fetch time.
- Pytest coverage for the limits, the gate, the orchestrator, and the HTTP/WebSocket surface. Tests use injected snapshots and a fake HTTP transport.

Not implemented yet:

- Real Hyperliquid order adapter
- Solana / Pump.fun adapters
- Wallet signing isolation
- Authenticated public hosting for the dashboard

The local dashboard is in `frontend/`. It is rule-based and shows no secrets. It is not a login wall.

Also not in this phase: exchange position sync, a live fee schedule, an LLM analyst, authentication on the API, and any path that contacts an RPC. The paper account in SQLite is local desk state, not an exchange balance. The market-data client is capable of calling the public info endpoint, but the automated tests never do; they mock the transport. Do not treat a dry-run journal row as a fill.

## Architecture

```mermaid
flowchart LR
  idea[Idea] --> desk[Desk Lead]
  desk --> market[Market Analyst]
  desk --> research[Research Analyst]
  market --> strat[Strategist]
  research --> strat
  strat --> riskMgr[Risk Manager]
  riskMgr --> engine[Risk Engine]
  engine --> exec[Execution Trader]
  exec --> gate[Execution Gate]
  gate --> dry[DryRunAdapter]
  exec --> review[Trade Reviewer]
```

The risk engine is a separate module. The Risk Manager agent only calls it. A proposal can ask for 100% of equity minus round-trip costs; the engine still rejects the order when that breaches the reserve, the planned-risk cap, or any other rule.

Market snapshots carry `source` and `fetched_at`. The orchestrator does not fetch prices itself. If a snapshot is missing, the Market Analyst stops and does not invent a mid. Age for the risk check is the earlier of the local fetch time and the exchange timestamp when both exist.

## Agents

All seven are `rule_based`.

| Agent | Role |
| --- | --- |
| Desk Lead | Accepts a Hyperliquid idea and opens a case. Other venues are rejected. |
| Market Analyst | Reads bid, ask, and sizes. Wide spreads and stale books are not tradable. A mid with no book is not a signal. |
| Research Analyst | Uses only structured fields the caller supplied (`trend`, `funding_bps`). Free-text notes are stored and not scored. |
| Strategist | Builds an order. `risk_limited` uses the tightest of balance, reserve, and planned-risk bounds. `all_in` uses 100% of equity minus costs and can be rejected. |
| Risk Manager | Passes the order to the risk engine and returns that decision. |
| Execution Trader | Dry-runs a `PASS`. Live mode must clear the gate and is still not transmitted. |
| Trade Reviewer | Writes the journal entry. |

## Risk limits

Defaults, overridable by environment except leverage, which is fixed at 1:

| Rule | Default |
| --- | --- |
| Starting capital | 20 CHF |
| Leverage | must equal 1 |
| Planned loss per trade | 1% of equity, including round-trip fees and slippage |
| Daily realized loss | 3% of start-of-day equity blocks new entries once hit |
| Open positions | 1 |
| New entries per day | 2 |
| Hyperliquid reserve | at least 20% of equity left as free collateral after notional, fees, and slippage |
| Minimum notional | 10 USD, the Hyperliquid minimum order value given for this desk |
| Stale data | older than 5 seconds, or a timestamp more than 2 seconds in the future |
| Duplicate protection | a client order id is consumed on first sight |
| Kill switch | persisted in SQLite; blocks every new order, including reduces, while engaged |

Planned loss is `notional * stop distance / entry + notional * fee bps / 10000 + notional * slippage bps / 10000`. Fee and slippage inputs below the configured assumptions are raised to those assumptions, so a caller cannot zero them out. Default assumptions are 10 bps round-trip fees and 10 bps round-trip slippage. Those are desk assumptions, not a live fee table.

Hyperliquid cash is fully funded. Leverage does not reduce the collateral the engine holds back. Free collateral after the order must remain at least 20% of equity.

If the paper account is CHF and the minimum is 10 USD, the order must include `usd_per_notional_currency`. The engine does not invent an FX rate. The notional itself must already be in the account currency.

## Execution gate

`LIVE_TRADING_ENABLED` defaults to `false` (`LIVE_TRADING_ENABLED` or `HYPERGROK_LIVE_TRADING_ENABLED`).

- Dry-run orders are recorded by `DryRunAdapter` and marked `transmitted: false`.
- A live order while the flag is off is rejected with `live_trading_disabled`.
- A live order while the flag is on, without a matching unused approval token for that client order id, is rejected with `missing_human_approval`.
- A live order with a valid token is rejected with `live_transmission_not_implemented`. The token is not consumed. Nothing is signed or sent.

Create a token with `POST /api/approvals` and pass it on that one idea as `approval_token`. Tokens are redacted in logs and in the journal payload.

## Coinbase spot

Create a CDP API key in the Coinbase Developer Platform with only **View** and **Trade**. Do not enable Transfer, Withdraw, or Convert. Download the JSON key and keep it outside the repository.

```bash
export COINBASE_API_KEY_FILE=/secure/path/cdp_api_key.json
# or COINBASE_API_KEY_NAME=organizations/.../apiKeys/... and COINBASE_API_PRIVATE_KEY=...
export LIVE_TRADING_ENABLED=false
export COINBASE_LIVE_ENABLED=false
export COINBASE_PRODUCT_ALLOWLIST=
export COINBASE_MAX_CAPITAL=0
```

Live spot orders also need `LIVE_TRADING_ENABLED=true`, `COINBASE_LIVE_ENABLED=true`, a non-empty product allowlist, `COINBASE_MAX_CAPITAL` greater than 0, and a per-order approval token from `POST /api/approvals`. Anything missing stays on the dry-run adapter. Other venues still return `live_transmission_not_implemented`.

CHF notionals are not converted with a guessed rate. Set both `HYPERGROK_FX_USD_PER_CHF` and `HYPERGROK_FX_AS_OF`, or read Coinbase public `v2/exchange-rates`. A missing or stale quote rejects the conversion. Product minimums and increments come from product metadata. Fees in the risk check come from the transaction-summary maker/taker rates. P&L is average cost from fills, with fees in the cost basis, at `GET /api/coinbase/portfolio`.

The kill switch still blocks new orders. When Coinbase live flags and credentials are present it also cancels open spot orders. It does not withdraw.

```bash
cd frontend
npm install
npm test
npm run dev
```

## HYPERGROK LIVE CONTROL

`monitor/` is a separate read-only page. It does not place orders, toggle the kill switch, or show keys. GitHub Pages cannot password-protect a public site; the page only shows data that is already public, plus desk telemetry if you point it at your own backend. There is no client-side password.

```bash
cd monitor
npm install
npm test
npm run dev
```

Optional: `VITE_BACKEND_URL=http://127.0.0.1:8000 npm run dev`. Without that URL the page says `Backend nicht verbunden` and `Keine Daten`. Cursor agent status has no public unauthenticated endpoint, so the card stays `Nicht verfügbar` and links to the agent run.

GitHub data uses the public REST API. The page re-reads its cache about every 90 seconds and calls GitHub at most every 4 minutes, because one refresh is four requests and unauthenticated traffic is limited to 60 requests per hour. A 403 or 429 keeps the cache and does not invent commits.

`.github/workflows/pages.yml` deploys `monitor/dist` with GitHub Actions. Pages only publishes the default branch, so the site is not live from this pull request. This environment cannot enable Pages or merge to `main`.

Timestamps use `Europe/Zurich`. Checklist progress is the count of items in `monitor/src/status.json`, not an estimated project percentage.

### iPhone

On the same Wi-Fi as the computer, run the backend with `--host 0.0.0.0` and `cd monitor && VITE_BACKEND_URL=http://<computer-lan-ip>:8000 npm run dev -- --host 0.0.0.0`. Open `http://<computer-lan-ip>:5173` on the phone. That address is not public HTTPS. The monitor does not show balances or keys. If `VITE_BACKEND_URL` is unset, ideas and risk stay `Keine Daten`. The Coinbase price card uses the public exchange ticker and shows `Keine Daten` when that request fails. Cursor status stays `Nicht verfügbar`.

### GitHub Pages

Pages is not enabled (`GET /repos/Nate8645/HYPERGROK-AI-EMPIRE/pages` returned 404 on 2026-11-09). To turn it on yourself, after this pull request is merged to `main`:

1. Open the repository Settings, then Pages.
2. Set the source to GitHub Actions.
3. The workflow `.github/workflows/pages.yml` runs only on pushes to `main`. It builds `monitor/` with `VITE_BACKEND_URL` empty. Do not add a backend URL, a key, or an account balance to that workflow.

This session cannot change those settings and cannot merge to `main`.

### Free HTTPS for the backend

The desk has no authentication. A public URL makes the kill switch and paper account reachable by anyone who has the URL.

- Same-LAN HTTP, as above, needs no account and is not HTTPS.
- Cloudflare Tunnel (`cloudflared`) can expose localhost over HTTPS. A named tunnel needs a free Cloudflare account. `cloudflared tunnel --url http://127.0.0.1:8000` gives a temporary URL and still requires installing their client.
- ngrok and localtunnel also need an install. ngrok’s stable HTTPS address needs a free account. Treat all of these as untrusted until you add your own access control. Do not put the tunnel URL into the Pages build.

## Setup

Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional; the file must not contain secrets
PYTHONPATH=backend uvicorn hypergrok.main:create_app --factory --host 127.0.0.1 --port 8000
```

The default database is `sqlite:///./data/hypergrok.db`, created on startup. The API has no authentication. Keep it on localhost.

Useful routes:

- `GET /health`
- `WS /ws/events`
- `GET /api/agents/status`
- `GET /api/risk/config`
- `GET /api/risk/account` and `PUT /api/risk/account` (paper state)
- `GET` and `POST /api/risk/kill-switch`
- `POST /api/risk/evaluate`
- `POST /api/desk/run`
- `GET /api/journal`
- `POST /api/approvals`
- `GET /api/execution/attempts`

`POST /api/desk/run` expects the market snapshot in the body. It does not call Hyperliquid. The info client is available as `hypergrok.marketdata.HyperliquidInfoClient` for a later wiring step.

## Tests

```bash
pytest
```

GitHub Actions (`.github/workflows/ci.yml`) runs the same command on Python 3.11.

## Safety

Do not commit private keys, seed phrases, or exchange API keys. `.env` is gitignored. `.env.example` has none. Phase 1 dependencies are FastAPI, Uvicorn, Pydantic, SQLAlchemy, HTTPX, and pytest. There is no signing library.
