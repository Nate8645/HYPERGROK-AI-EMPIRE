# Development status

Updated 2026-11-09 after the full-capital simulation. The 1% loss rule is unchanged. Autonomous mode is unset. Live trading stays blocked.

## Phase 1 — desk backend

- Status: implemented, tested. Not deployable as a public service (no authentication).
- Live trading: blocked.

## Phase 2 — Coinbase spot adapter and desk UI

- Status: implemented, tested. Live arming blocked by configuration.
- `coinbase-advanced-py==1.8.4`. Gates default off. Allowlist empty. Capital cap 0.

## Phase 2b — HYPERGROK LIVE CONTROL

- Status: implemented and tested as a static app. GitHub Pages deploy is blocked.
- Pages API returned 404. The workflow runs only on `main`.

## Phase 3 — research and rules

- Status: implemented and tested locally. Not a live-trading approval.
- Repo audit: `docs/research/REPO-AUDIT.md`.
- Indicators, long-only backtests, research checks, SQLite blackboard, and a preview-only pipeline.
- Public daily candles for BTC-USD, ETH-USD, and SOL-USD from 2025-11-25 through 2026-11-09 were fetched from `api.exchange.coinbase.com` and saved in `docs/research/backtests/public-candles.json`. Every strategy in that file carries `too_few_trades`. These are not return promises.
- LangGraph and CrewAI were not installed. No model budget is configured.
- Orchestration is a plain Python pipeline.

### Tests actually run

- `pytest`: 71 passed, 1 Starlette deprecation warning, about 1.3s, Python 3.12.3.
- `frontend` vitest: 5 passed. Production build succeeded.
- `monitor` vitest: 8 passed. Production build succeeded.
- `pip-audit -r requirements.txt`: pytest 8.4.2 had PYSEC-2026-1845. Requirements now pin pytest 9.0.3, and the suite was re-run after that pin.
- `npm audit` in `frontend/` and `monitor/`: 6 findings each (3 moderate, 1 high, 2 critical), all requiring a major Vitest 5 upgrade. Not upgraded in this change.
- Secret scan of source text for PEM blocks and 64-hex `0x` keys: no hits. `gitleaks` was not installed.

### Open bugs

- Vitest/Vite dev-dependency advisories remain.
- Backtest samples are too small for Sharpe and are flagged for too few trades.
- The desk API has no authentication. Do not expose it on the internet.

### Blockers

- Real-money trading is blocked. The user has not given activation approval.
- GitHub Pages is not enabled.

## Phase 4 — HYPERGROK LIVE CONTROL

- Status: implemented and tested as a static app. Deployable only after you merge to `main` and enable Pages. The hosted URL is blocked.
- iPhone layout uses a single column under 700px and safe-area padding.
- Seven agents, ideas, and risk render from the backend only when `VITE_BACKEND_URL` is set. Otherwise they show `Keine Daten` and do not animate.
- Coinbase prices come from the public exchange ticker. A failed request shows `Keine Daten`.
- GitHub commits, PR state, and Actions status use the public API with a four-minute cache.
- Cursor status is `Nicht verfügbar`. No public unauthenticated status API was found.
- Pages steps and free tunnel options are in the README. Cloudflare Tunnel, ngrok, and localtunnel need an install; named or stable HTTPS addresses need a free account. Same-LAN HTTP needs no account and is not HTTPS.

### Tests actually run for this phase

- `monitor` vitest: 9 passed. Production build succeeded.

## Phase 5 — integration and QA

- Status: implemented and tested locally. A public deployment is blocked: the API has no authentication, Pages is not enabled, and this session does not change repository settings.
- `backend/tests/test_integration.py` runs health, the seven agents, Coinbase status, a desk run, and the preview pipeline against one app. The live request is rejected by the execution gate.
- README has the local startup commands for the API, the desk UI, and the iPhone path on the same Wi-Fi.

### Tests actually run for this phase

- Full pytest with coverage: 72 passed. `hypergrok` line coverage 85% (3249 statements, 477 missed).
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- `npm audit --omit=dev` in `frontend/`: 0 vulnerabilities. The full audit, including Vitest, reports 6 (3 moderate, 1 high, 2 critical) in the dev dependency tree. The offered fix is Vitest 5.1.0, a major bump. It was not applied.
- `monitor` has the same 6 dev-dependency findings. Production `npm audit --omit=dev` was checked on `frontend` only; `monitor` has no production runtime dependencies beyond Vite, which is a dev dependency there.
- Secret scan for private-key blocks and common token prefixes: the only hit is the test assertion that the monitor source must not contain `BEGIN PRIVATE KEY`.

## Phase 6 — real-money readiness, technical only

- Status: implemented and tested with a mocked Coinbase client. Deployable for live orders: blocked. `LIVE_TRADING_ENABLED` and `COINBASE_LIVE_ENABLED` stay false in the default configuration. The product allowlist default is empty and the capital cap default is 0. No live write call was made.
- Risk Manager remains the only path that records a pass the broker will accept.
- The execution gate still requires the live flags, a non-empty allowlist, a capital cap above 0, and a one-time approval token. The kill switch blocks new orders and, when the live flags and a client are present, cancels open spot orders.
- Duplicate protection is the `client_order_id`. A second evaluation is rejected.
- Stale market data is rejected by the risk engine.
- Capital cap 0 is rejected with `capital_cap_exceeded`.
- Product `base_min_size`, `quote_min_size`, `base_increment`, and `quote_increment` are enforced by `prepare_order_sizes`.
- A live place writes `dispatch_started` to SQLite before the network call. A new broker loaded from that database reconciles the id and does not call `market_order` again, including when the first result was unknown.
- `check_key_permissions` reads the mocked `get_api_key_permissions` response (the SDK method for `GET /api/v3/brokerage/key_permissions`). `can_transfer: true` rejects the order and clears `live_armed`.

### Tests actually run for this phase

- Full pytest: 75 passed, 1 warning (`StarletteDeprecationWarning` about httpx).
- Frontend vitest: 5 passed. Monitor vitest: 9 passed.
- New cases: `test_base_minimum_and_increments`, `test_transfer_permission_refuses_to_arm`, `test_restart_reconciles_and_does_not_resend`.

### Open bugs

- Node 20 deprecation annotations on GitHub Actions. The jobs use Node 20. This does not fail the suite.
- Vitest 2.1.9 dev dependencies report 6 npm audit findings. Production `npm audit --omit=dev` in `frontend/` is clean. The fix is a major upgrade to Vitest 5.1.0, which was not applied.

### Blockers for a live desk

- You have not enabled a View+Trade CDP key outside the repo.
- You have not set the live flags, a product allowlist, or a capital cap, and you should not until you intend to send real spot orders.
- The key-permission check refuses a transfer-capable key only after it is invoked. It was not called against Coinbase.
- The API has no authentication.
- GitHub Pages is not enabled. The workflow deploys only from `main`.

## Coinbase BUY/SELL extension

- Status: implemented and tested with mocks. Live submit is blocked. A public dashboard is blocked.
- Read-only account facts from 2026-11-09 21:37 Europe/Zurich are a fixture, not a live default. See `docs/COINBASE_READINESS.md`.
- Market and limit buy/sell, preview, `get_order` confirmation, fills, and fee-inclusive P&L stay on the existing adapter.
- `GET /api/coinbase/utilization` sizes 10/25/50/75/100% of the quote balance returned by the API. Without a configured client it returns `Keine Daten`.
- `POST /api/desk/team` runs all seven agents and, when a client exists, a preview. It does not submit while the live flags are off.
- The local desk in `frontend/` shows cash, portfolio, prices, signals, fees, P&L, risk, utilization, open orders, fills, and a per-order approval form. `monitor/` still has none of the private account data.

### Tests actually run for this extension

- Full pytest: 81 passed, 1 Starlette warning.
- New file: `backend/tests/test_spot_cases.py`.

### Open bugs

- Node 20 deprecation annotations on GitHub Actions. The jobs use Node 20. This does not fail the suite.
- Vitest 2.1.9 dev dependencies report 6 npm audit findings. Production `npm audit --omit=dev` in `frontend/` is clean. The fix is a major upgrade to Vitest 5.1.0, which was not applied.

### Blockers for a live desk

- You have not enabled a View+Trade CDP key outside the repo.
- You have not set the live flags, a product allowlist, or a capital cap, and you should not until you intend to send real spot orders.
- The key-permission check refuses a transfer-capable key only after it is invoked. It was not called against Coinbase.
- The API has no authentication.
- GitHub Pages is not enabled. The workflow deploys only from `main`.
- The read showed USDC only. There is no crypto position to sell.
- No USDC-pair backtest exists. The utilization panel says `Keine Daten` for those products.

## Full-capital simulation and activation fields

- Status: implemented and tested. Not an order permission. Deployable for live trading: blocked.
- `full_capital_size` reserves the entry fee and the exit fee, then rounds down to 0.01. On 10.896768 USDC at a 0.001 taker rate both sides, the size is 10.87.
- The Risk Manager simulation rejected that size. Daily gaps in the BTC-USD sample would break the 1% budget in 71.3% of sessions. One-minute noise was smaller than the required 0.6024% stop, so that particular reject reason did not fire. Details are in `docs/COINBASE_READINESS.md`.
- Autonomous arming stays locked. Every required field is UNSET. Proposed values are only in `docs/ACTIVATION_SUMMARY.md`.
- Exits preview a stop-limit or market sell and store an approval. They do not submit. A feed outage, stale book, or engaged kill switch produces no preview.
- `run_final_preview_case` runs market, research, strategist, desk lead, risk, execution, and review with live submission forced off. The live preview is `Keine Daten`.

### Tests actually run

- Full pytest: 88 passed, 1 Starlette warning.

### Next step

`docs/ACTIVATION_SUMMARY.md` is the binding checklist. Every prerequisite there is MISSING. The three live flags stay false. Do not merge from this workspace. Do not turn autonomous mode on from this workspace.

### Resume point

Branch `cursor/phase1-desk-backend-716c`, PR https://github.com/Nate8645/HYPERGROK-AI-EMPIRE/pull/1. Uncommitted working-tree edits add session auth and the audit tests; `test_audit_191ff29.py` passed 9 tests, and `test_api.py` then failed because those tests do not log in. Finish that auth work and get the full suite green before treating authentication as met.

### Resume point

Branch `cursor/phase1-desk-backend-716c`, PR https://github.com/Nate8645/HYPERGROK-AI-EMPIRE/pull/1.
