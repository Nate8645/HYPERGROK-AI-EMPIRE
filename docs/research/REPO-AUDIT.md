# Repository audit

Checked on 2026-11-09 with the public GitHub API (`gh api repos/...`). These repositories were read as research only. No source was copied into HyperGrok.

| Repository | Accessible | License | Last push (UTC) | Tests | Paid or external cost | Suspicious notes | Reuse |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zostaff/grok-trading-desk | yes, public | none declared | 2026-08-30 | yes, pytest under `tests/` | xAI search and Grok calls; Alpaca; Solana RPC | LLM agents with a JSON veto. `solders`/`solana` in requirements. No license, so code cannot be copied. | Idea only: a failed model must reject, not approve. Already matches our risk gate. |
| galleonlabs/hypergrok-trading-desk | yes, public | MIT | 2026-11-04 | yes, script tests including an exchange write gate | Host LLM (Grok, Claude, Codex, Gemini) is paid by the operator | Seven role profiles and keyless Hyperliquid tools. Human approval before send. | Idea only, with attribution if any text were copied. We did not copy files. The seven-role order and approval ticket match the desk we already run. |
| swcstudiospace/PumpGrok | yes, public | AGPL-3.0 | 2026-11-08 | yes, large pytest tree | x.ai Grok, Jupiter, Solana RPC | Paper ledger, risk veto, human ticket. AGPL would cover derivative copies. | Not copied. Risk veto and paper-first are already our defaults. |
| GrokDesk/grokdesk | yes, public | MIT | 2026-09-01 | no test files found | optional OpenAI-compatible HTTP only | Paper trading, no wallet. README says no network required for paper mode. | Not copied. Confirms a paper desk can stay on the standard library. |
| kayzaa/k.i.t.-bot | yes, public | MIT | 2026-02-22 | some vitest and ad-hoc scripts | Anthropic SDK, Google Generative AI, CCXT exchanges | `postinstall` runs `scripts/setup.js`, which creates `~/.kit/credentials`. Not clear exfiltration, but an install script that touches a credentials directory is not acceptable to vendor. | Not used. |
| Trilokx/fomo-family-cli | no | n/a | n/a | n/a | n/a | GitHub API returned 404. | Nothing. |
| jfferreira97/fomofaster-ws | yes, public | none declared | 2026-10-29 | no project test suite; migration and a static HTML probe only | Telegram, Playwright against fomo.family and pump.fun | Sidecars scrape or subscribe to third-party feeds. No license. | Not used. |
| Nate8645/HYPERGROK-TRADING-EMPIRE-V2 | no | n/a | n/a | n/a | n/a | GitHub API returned 404 for this account. | Nothing. |
| crewAIInc/crewAI | yes, public | MIT | 2026-11-09 | yes, large suite | CrewAI cloud and any LLM provider the crew calls | Framework assumes language-model agents. | Not installed. No budgeted LLM is configured here. |
| langchain-ai/langgraph | yes, public | MIT | 2026-11-09 | yes | LangSmith and model providers are optional and paid | Graph runtime for stateful agents. | Not installed. A straight Python pipeline is enough for a fixed desk order. |

## Compatible libraries that were not imported

| Project | License seen | Why it was not added |
| --- | --- | --- |
| polakowo/vectorbt | GitHub SPDX `NOASSERTION` (the public project is not a clean OSI grant; PRO is commercial) | Indicator and backtest math was reimplemented. |
| kernc/backtesting.py | AGPL-3.0 | Copyleft. Walk-forward and cost-aware fills were reimplemented. |
| pandas-ta | repository name returned 404 on 2026-11-09 | Not required. |

No paid data vendor was added. Candle reads, if they succeed, use Coinbase's public market endpoint.

## Prioritized improvements

1. Deterministic indicators and book metrics, with tests against hand-calculated values.
2. A long-only spot backtester with fees, slippage, splits, walk-forward, and an overfitting warning.
3. Research rules for regime, data quality, and cross-agent conflicts, each input stamped with source and time.
4. SQLite blackboard, structured messages, and a decision log around the existing pipeline. Execution stays preview/dry-run.
5. Reviewer metrics from journal and backtest trades, with Sharpe withheld on small samples.
6. Monitor panels that show those facts or `Keine Daten`.

LangGraph and CrewAI were not adopted. Both are built to drive model calls. This desk has no authorized model budget, and the agent order is fixed, so a plain function pipeline is the orchestration.
