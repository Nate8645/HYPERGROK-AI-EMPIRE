# Development status

Updated 2026-11-09 after Phase 4. Phases 5–6 are not started.

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

### Next step

Phase 5, coverage and the local iPhone startup guide. Resume from this file.

### Resume point

Branch `cursor/phase1-desk-backend-716c`, PR https://github.com/Nate8645/HYPERGROK-AI-EMPIRE/pull/1.
