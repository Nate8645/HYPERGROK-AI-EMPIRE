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
| Security tests passed | **MISSING** | The audit tests and the authenticated API tests pass in this workspace. That is not a production sign-off. No operator password hash is configured outside the test helper. |
| Authenticated endpoints | **MISSING** | Login, logout, and role checks are in the branch. Anonymous calls to the trial route return 401. A production password hash is still unset, so a deployed desk stays locked until you set one. |
| All 8 limits confirmed by the user | **MISSING** | You have not confirmed any of them. Each field below is **UNSET**. The simulated trial did not write them. |
| Working kill switch | **MISSING** | The paper kill switch rejects the next simulated order (`docs/research/trial-run-simulated.json`, `kill_switch.blocked` true). No live cancel was sent. Both live flags are false. |
| Secure key storage | **MISSING** | The desk can read `COINBASE_API_KEY_FILE` or env vars. This process has no CDP key. The Coinbase order preview is **NOT RUN**. |
| CDP key with View and Trade only, without Transfer | **MISSING** | The code can refuse `can_transfer` on a mocked permissions response. This session did not call the live key-permissions endpoint. Transfer permission is unknown. |
| A strategy that is demonstrably admissible | **MISSING** | Explicit result: **NO TRADE**. Hourly and 15-minute screens of BTC-USD, ETH-USD, and SOL-USD, latest 2,000 bars, have no robust row. BTC-USD hourly 10% expectancies are negative. A 5% stop on 100% of 10.896768 USDC violates the 1% budget. The largest size inside that budget is 2.05 USDC. It clears the 1 USDC product minimum and is not a buy signal. |
| A separate final activation through the protected UI | **MISSING** | The protected dashboard can show the saved trial, labelled SIMULATED. The form does not arm the desk. You have not submitted an activation. |

Activation stays blocked until every row is MET and you then set the flags yourself.

## The 8 limits

None of these rows is approved. A proposed value is not a confirmation.

| Limit | Status | Technical evidence | Missing steps | Required user approval |
| --- | --- | --- | --- | --- |
| Max loss per trade | **UNSET** | The risk engine default is 1% of equity (`max_planned_risk_fraction`). On 10.896768 USDC that is 0.10896768 USDC. The 100% simulation was REJECT. | You type the number in the protected activation form. The server does not copy the default in. | Confirm 1%, or write a different fraction. |
| Max loss per day | **UNSET** | The risk engine default is 3% of start-of-day equity. It is not stored as an autonomous field. | You type the daily limit. | Confirm 3%, or write a different fraction. |
| Max total loss | **UNSET** | No total-loss field is set. No written total exists in the desk brief. | You choose a number. None is proposed. | Write the total-loss cap yourself. |
| Max deployed capital | **UNSET** | `coinbase_max_capital` is 0. `autonomous_max_deployed_capital` is empty. Paper starting capital is CHF 20. The read balance is 10.896768 USDC. No FX rate was applied. | You set the cap in the form and in the environment. | Confirm whether the cap is CHF 20 or 10.896768 USDC. |
| Allowed pairs | **UNSET** | `COINBASE_PRODUCT_ALLOWLIST` is empty. `autonomous_allowed_pairs` is empty. | You list the pairs. | Confirm BTC-USDC, ETH-USDC, and SOL-USDC, or name others. |
| Expiry timestamp | **UNSET** | `autonomous_expires_at` is empty. A past mandate already fails login in `test_p1_expired_mandate_rejects_login`. | You choose a future timestamp. | Write the expiry. No date is proposed. |
| Max slippage | **UNSET** | The desk assumption is 10 bps per side. That is not an autonomous setting and not a live measurement. | You type the bps cap. | Confirm 10 bps per side, or write another cap. |
| Kill-switch conditions | **UNSET** | The kill switch blocks new orders when engaged. Suggested ids are `manual_halt`, `daily_loss`, `stale_data`, `feed_outage`. They are not stored. | You enter the condition list. | Confirm that list, or replace it. |

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

## Simulated trial on 2026-11-09

The same USDC available balance, 10.896768, was read again. Hold remains 0. BTC, CHF, and EUR available remain 0. Account identifiers are omitted. The desk has no CDP key, so the Coinbase order preview is **NOT RUN**.

Public books were read from `https://api.coinbase.com/api/v3/brokerage/market/product_book` and saved in `docs/research/public-books-2026-11-09.json`. The seven rule-based agents ran on that snapshot. The artifact is `docs/research/trial-run-simulated.json`. Its label is **SIMULATED**. `transmitted` is false. The three flags are false.

The protected dashboard route `GET /api/desk/simulated-trial` returns that file only after login. It does not submit an order.

Activation remains blocked. The missing items are the eight limits above, a production password hash, a CDP key stored outside the repo with View and Trade only, an allowlist, a capital cap you choose, and a strategy that passes the screen. None of those is present.
