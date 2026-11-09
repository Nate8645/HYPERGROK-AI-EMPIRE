# Activation overview

This file is the binding checklist for real-money activation. A line is **MET** only when the evidence cited here exists. Every other line is **MISSING**. Real-money trading is **not approved**.

This update does not change configuration. These three flags stay **false**:

| Flag | Code default | This update |
| --- | --- | --- |
| `LIVE_TRADING_ENABLED` | `false` | left false |
| `COINBASE_LIVE_ENABLED` | `false` | left false |
| `AUTONOMOUS_ENABLED` | `false` | left false |

No limit in the table below has been written into the running configuration.

## Checklist

| Prerequisite | Status | Evidence |
| --- | --- | --- |
| Security tests passed | **MISSING** | On 2026-11-09, `backend/tests/test_audit_191ff29.py` passed 9 tests (unauthenticated and viewer denial, expired mandate, bound and expiring approval, stale or modified risk pass, direct adapter without a grant, concurrent claim, unknown-result restart, exit gap without a guaranteed fill). Immediately after that, `backend/tests/test_api.py` failed: the new session check rejects those tests because they do not log in. The full suite has not been green since that edit, and the edit is not committed. |
| Authenticated endpoints | **MISSING** | Session login, role checks, and locks on approvals, orders, the kill switch, account updates, balances, and `/ws/events` exist only in the uncommitted working tree. Anonymous calls in the audit tests return 401 or 403. There is no committed build in which the rest of the API tests pass with that lock, and no password hash is configured for a real operator. |
| All 8 limits confirmed by the user | **MISSING** | You have not confirmed any of them. Each field below is **UNSET**. Proposed text is not applied. |
| Working kill switch | **MISSING** | On commit `191ff29` the paper kill switch was tested (`test_kill_switch_blocks_and_then_releases_orders`, `test_kill_switch_persists_across_a_new_process`, and the Coinbase cancel test). Those API tests currently fail because they are unauthenticated. No live cancel was sent. Both live flags are false. |
| Secure key storage | **MISSING** | The desk can read `COINBASE_API_KEY_FILE` or env vars, and the repo has no CDP key. This environment has no key file configured. A hash for the desk login is also unset outside the test helper. |
| CDP key with View and Trade only, without Transfer | **MISSING** | The code can refuse `can_transfer` when a mocked `get_api_key_permissions` response says so. This session did not call that endpoint on the live key. Transfer permission is therefore unknown, not proven absent. |
| A strategy that is demonstrably admissible | **MISSING** | Explicit result: **NO TRADE**. The 100% size on 10.896768 USDC was rejected because 71.3% of BTC-USD daily gaps in the 2025-11-25 through 2026-11-09 sample would break the 1% loss budget. Out-of-sample daily comparisons for 2026-09-01 through 2026-11-09 did not produce a robust strategy. The 1% rejection was not removed. |
| A separate final activation through the protected UI | **MISSING** | No protected activation has been submitted by you. The UI cannot turn the three flags on. Autonomous mode stays false even if the form is filled in later. |

Activation stays blocked until every row is MET and you then set the flags yourself.

## The 8 limits

Confirmed by you: **no**.

| Limit | Config now | Proposed only, not applied |
| --- | --- | --- |
| Max loss per trade | **UNSET** | 1% of equity. That is CHF 0.20 on the CHF 20 paper rule, or 0.10896768 USDC on the balance below. |
| Max loss per day | **UNSET** | 3% of equity. |
| Max total loss | **UNSET** | No written total exists. None is proposed. |
| Max deployed capital | **UNSET** | The paper rule is CHF 20. The read balance is 10.896768 USDC. No FX conversion is applied, so the proposed cap is that USDC balance. |
| Allowed pairs | **UNSET** | BTC-USDC, ETH-USDC, SOL-USDC. |
| Expiry timestamp | **UNSET** | No expiry was written. None is proposed. |
| Max slippage | **UNSET** | 10 bps per side, the desk assumption. Not a live slippage measurement. |
| Kill-switch conditions | **UNSET** | `manual_halt`, `daily_loss`, `stale_data`, `feed_outage`. |

## Account facts read on 2026-11-09

Read through the Coinbase account connection during this update. Account identifiers are omitted. These figures are not saved as live defaults. The fee endpoint's rounded total balance was `10.90`. The available balance below is the figure to use.

| Item | Value |
| --- | --- |
| USDC available | 10.896768 |
| USDC on hold | 0 |
| BTC, CHF, EUR available | 0 |
| USD account in the response | none |
| Fee tier | Intro |
| Maker fee | 0.0009 |
| Taker fee | 0.001 |
| Fees paid in the fee response | 0 |

Minimum sizes, all three products `online`, product type `SPOT`:

| Product | quote_min_size | quote_increment | base_min_size | base_increment |
| --- | --- | --- | --- | --- |
| BTC-USDC | 1 | 0.01 | 0.00000001 | 0.00000001 |
| ETH-USDC | 1 | 0.01 | 0.00000001 | 0.00000001 |
| SOL-USDC | 1 | 0.01 | 0.00000001 | 0.00000001 |

Prices at the same read, not for order sizing: BTC-USDC 74810.2, ETH-USDC 2126.68, SOL-USDC 86.47.

A simulated 100% order that reserves the 0.001 taker fee on entry and on exit, then rounds down to 0.01, is 10.87 USDC. That simulation was rejected by the 1% rule. It was not sent.
