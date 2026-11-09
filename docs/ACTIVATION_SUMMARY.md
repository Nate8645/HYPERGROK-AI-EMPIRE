# Activation summary

Status of every autonomous-mode field: **UNSET**. Autonomous mode is disabled. Nothing in this file has been written into the running configuration. The existing desk limits are unchanged: 1% maximum planned loss, 3% daily loss, one open position, two entries per day, and leverage fixed at 1.

Confirm or reject each proposed value yourself before any field is set.

| Field | Config now | Proposed value, for confirmation only |
| --- | --- | --- |
| Autonomous mode | UNSET (`false`) | Leave off |
| Max loss per trade | UNSET | 1% of equity. On the CHF 20 paper rule that is CHF 0.20. On the 2026-11-09 USDC read, 1% of 10.896768 USDC is 0.10896768 USDC. |
| Max loss per day | UNSET | 3% of equity. No separate number was copied into the autonomous config. |
| Max total loss | UNSET | No written total-loss figure exists. None is proposed. |
| Max deployed capital | UNSET | The paper rule is CHF 20. The read balance is 10.896768 USDC available. No FX rate is applied here, so the proposed cap is that USDC balance, not a converted franc amount. |
| Allowed pairs | UNSET | BTC-USDC, ETH-USDC, SOL-USDC, because the read balance is USDC. |
| Expiry timestamp | UNSET | No expiry was written. None is proposed. |
| Max slippage | UNSET | 10 bps per side, the existing desk assumption. The saved BTC-USDC book spread was about 0.0013 bps and is not a slippage limit. |
| Kill-switch conditions | UNSET | `manual_halt`, `daily_loss`, `stale_data`, `feed_outage`. The kill switch still blocks new orders when it is engaged. |

`simulation_max_capital_fraction` defaults to 1 so a research run can *test* a fully funded order. The execution gate does not read it. It does not replace the 1% loss rule, and it does not arm autonomous mode.

A 100% order on 10.896768 USDC, after reserving the 0.1% taker entry fee and the 0.1% taker exit fee and rounding down to 0.01, is 10.87 USDC. The Risk Manager simulation rejected it. See `docs/COINBASE_READINESS.md`.
