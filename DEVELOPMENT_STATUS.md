# Development status

Updated 2026-11-09 after session auth, the 191ff29 audit fixes, logout, and the NO TRADE screen. The 1% overshoot REJECT is unchanged. The three live flags stay false.

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

## Phase 7 — hardening

- Status: tested locally. Not approved for real money. The binding checklist in `docs/ACTIVATION_SUMMARY.md` is still all MISSING.
- Private routes require a session. Logout deletes that session on the server. Tests use `authed` and do not turn auth off.
- Audit record: `docs/security/AUDIT-191ff29.md`. P1–P6 are fixed in tests. Residual risks are in that file.
- Coinbase SDK 1.8.4 signatures used by the broker match the installed client. Leverage is not passed.
- The public BTC-USD daily screen, with RSI, MACD, EMA, ATR, regime, and the saved book, is **NO TRADE**. VWAP is `Keine Daten` on that file because the saved daily bars have no volume. 100% sizing does not fit the 1% rule.
- The desk UI hides balance, orders, journal, the kill switch, and the activation form until sign-in. The activation form starts empty and does not arm the desk.
- `pip-audit -r requirements.txt`: no known vulnerabilities. `npm audit` in `frontend/` and `monitor/`: 6 findings each, all in the Vitest 2 dev tree. The offered fix is Vitest 5, a major upgrade. It was not applied. `npm audit --omit=dev` in `frontend/` was clean on the earlier run.

### Tests actually run

- pytest: 100 passed, 1 Starlette warning.
- frontend vitest: 7 passed. Production build succeeded.
- monitor vitest: 9 passed. Production build succeeded.

## Intraday screen and simulated trial

- Status: tested locally. Simulated. Not approved for real money. Activation stays blocked. See `docs/ACTIVATION_SUMMARY.md`.
- Public candles with volume: `docs/research/intraday-candles-2026-11-09.json`. Hourly BTC-USD and ETH-USD have 36,337 bars, SOL-USD 36,335, from 2022-09-17 08:00Z through 2026-11-09 21:00Z. Fifteen-minute bars are 5,150 each, from 2026-09-17 06:00Z through 2026-11-09 21:15Z. The exchange still had older hourly bars, so this is the downloaded window.
- Strategy evaluation used the latest 2,000 bars because the research functions recompute indicators per bar. Stop-overshoot and gap stress used every downloaded bar. Outcome: **NO TRADE**. No row is robust. BTC-USD hourly 10% expectancies are negative (ema_cross -0.00726 on 22 trades, mean_reversion -0.00429 on 34, breakout -0.00274 on 9, momentum -0.00507 on 40). Walk-forward out-of-sample trade counts for that window are ema_cross 16 and 18, mean_reversion 31 and 44, breakout 27 and 16, momentum 52 and 54. Full-series hourly gap-stress share on a 0.6% move is 0.145. VWAP is present because these bars have volume.
- 25%, 50%, and 100% sizes recorded 0 trades on that window: a 5% stop on those fractions breaks the 1% budget.
- Seven rule-based agents ran Desk Lead first on the saved public USDC books. Artifact: `docs/research/agent-evidence-run.json`. BTC-USDC reached the Risk Manager and was REJECT. ETH-USDC and SOL-USDC stopped at a neutral book, so the Risk Manager entry is skipped. Nothing was transmitted.
- Simulated trial: `docs/research/trial-run-simulated.json`, label SIMULATED. Balance read: USDC available 10.896768, hold 0, BTC/CHF/EUR available 0. No desk CDP key, so the order preview is NOT RUN. Coinbase spot uses the cached product minimum (quote_min_size 1, quote_increment 0.01, base_min_size and base_increment 0.00000001). A missing or stale product is a reject. The 10 USD figure remains the Hyperliquid minimum only. On a 5% stop the largest size inside the 1% budget is 2.05 USDC, which clears the 1 USDC minimum and is not a buy signal. The decision stays NO TRADE because no strategy was robust. Mock buy and mock sell are recorded with transmitted false. The kill switch blocked the next evaluation. The protected dashboard loads this file at `GET /api/desk/simulated-trial` after login.
- The three flags stay false.

### Tests actually run

- pytest: 108 passed, 1 Starlette warning. The new cases cover per-product minimums, rounding, fees, FX, and missing or stale product data.
- frontend vitest: 8 passed. Production build succeeded.
- monitor vitest: 9 passed. Production build succeeded.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- `npm audit` in `frontend/` and `monitor/`: 6 findings each, all in the Vitest 2 dev tree. The offered fix is Vitest 5, a major upgrade. It was not applied.

### Next step

Your review of pull request 1. Do not merge from this workspace. Do not turn the three live flags on.

### Resume point

Branch `cursor/phase1-desk-backend-716c`, PR https://github.com/Nate8645/HYPERGROK-AI-EMPIRE/pull/1. Activation remains blocked. See `docs/ACTIVATION_SUMMARY.md`.
