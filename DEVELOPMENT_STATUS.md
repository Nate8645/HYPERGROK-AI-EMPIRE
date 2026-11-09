# Development status

Updated 2026-11-09 after Phase 5. Phase 6 is not started.

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

### Next step

Phase 6, mocked real-money readiness. Resume from `backend/hypergrok/venues/coinbase/broker.py` and `service.py`.

### Resume point

Branch `cursor/phase1-desk-backend-716c`, PR https://github.com/Nate8645/HYPERGROK-AI-EMPIRE/pull/1.
