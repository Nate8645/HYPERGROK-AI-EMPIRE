import { useState } from "react";
import type { AgentStatus, Balance, CoinbaseStatus, DeskFill, DeskOrder, JournalEntry, Portfolio, RiskConfig, Ticker, UtilizationVariant } from "./types";

export function LiveStatus({ status }: { status: CoinbaseStatus | null }) {
  if (!status) {
    return <section className="card"><h2>Live trading</h2><p className="bad">DISABLED</p><p>Coinbase status is not loaded.</p></section>;
  }
  const missing = status.prerequisites.filter((item) => !item.ok);
  return (
    <section className="card">
      <h2>Live trading</h2>
      <p className={status.live_armed ? "ok" : "bad"}>{status.live_armed ? "ARMED" : "DISABLED"}</p>
      <p>Rule-based desk. No language model places orders.</p>
      {missing.length > 0 && (
        <ul>
          {missing.map((item) => (
            <li key={item.id}>{item.detail}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function AgentBoard({ agents }: { agents: AgentStatus[] }) {
  return (
    <section className="card">
      <h2>Agents</h2>
      <div className="agents">
        {agents.map((agent) => (
          <article key={agent.key}>
            <strong>{agent.name}</strong>
            <span className="tag">rule-based</span>
            <span>{agent.status}</span>
            <p>{agent.last_summary ?? "No case yet."}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function BalanceCard({ state, balance }: { state: "loading" | "missing" | "ready"; balance: Balance | null }) {
  let text = "Loading balances.";
  if (state === "missing") {
    text = "not configured";
  } else if (balance?.account_state === "empty" || (balance?.accounts ?? []).every((row) => Number(row.available) === 0)) {
    text = "empty";
  } else if (balance?.accounts) {
    text = balance.accounts.map((row) => `${row.currency} ${row.available}`).join(" · ");
  }
  return (
    <section className="card">
      <h2>Coinbase balance</h2>
      <p>{text}</p>
    </section>
  );
}

export function PnlCard({ portfolio }: { portfolio: Portfolio | null }) {
  if (!portfolio) {
    return <section className="card"><h2>P&amp;L</h2><p>No portfolio snapshot.</p></section>;
  }
  return (
    <section className="card">
      <h2>P&amp;L</h2>
      <p>Fees included in cost basis. Average cost.</p>
      <p>Realized {portfolio.realized_pnl}</p>
      <p>Unrealized {portfolio.unrealized_pnl ?? "mark unavailable"}</p>
      <p>Fees {portfolio.fees}</p>
      <ul>
        {portfolio.positions.map((position) => (
          <li key={position.product_id}>
            {position.product_id} qty {position.quantity} basis {position.cost_basis} mark {position.mark_price ?? "unavailable"}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function RiskCard({ config }: { config: RiskConfig | null }) {
  if (!config) {
    return <section className="card"><h2>Risk</h2><p>Risk config is not loaded.</p></section>;
  }
  return (
    <section className="card">
      <h2>Risk limits</h2>
      <ul>
        <li>Planned risk {config.max_planned_risk_fraction} of equity</li>
        <li>Daily loss {config.max_daily_loss_fraction} of start-of-day equity</li>
        <li>Open positions {config.max_open_positions}</li>
        <li>New entries per day {config.max_new_entries_per_day}</li>
        <li>Leverage fixed at 1</li>
      </ul>
    </section>
  );
}

export function JournalCard({ entries }: { entries: JournalEntry[] }) {
  return (
    <section className="card">
      <h2>Journal</h2>
      {entries.length === 0 ? <p>No journal entries.</p> : (
        <ul>
          {entries.map((entry) => (
            <li key={entry.id}>{entry.outcome} {entry.symbol}: {entry.summary}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PriceCard({ bid, ask, source }: { bid: string | null; ask: string | null; source: string | null }) {
  return (
    <section className="card">
      <h2>Coinbase book</h2>
      <p>{bid && ask ? `Bid ${bid} / Ask ${ask}` : "No labelled book."}</p>
      <p>{source ?? "Source not loaded."}</p>
    </section>
  );
}

export function KillSwitch({ engaged, onToggle }: { engaged: boolean; onToggle: (next: boolean) => void }) {
  return (
    <section className="card">
      <h2>Kill switch</h2>
      <p>{engaged ? "Engaged. New orders are blocked." : "Disengaged."}</p>
      <button type="button" onClick={() => onToggle(!engaged)}>{engaged ? "Disengage" : "Engage"}</button>
    </section>
  );
}

export function PreviewCard({ message }: { message: string }) {
  return (
    <section className="card">
      <h2>Order preview</h2>
      <p>{message}</p>
    </section>
  );
}

export function TickerBoard({ tickers }: { tickers: Ticker[] }) {
  return (
    <section className="card">
      <h2>Live prices</h2>
      {tickers.length === 0 ? <p>Keine Daten</p> : tickers.map((ticker) => (
        <p key={ticker.product_id}>{ticker.product_id} {ticker.price ?? ticker.detail ?? "Keine Daten"}</p>
      ))}
    </section>
  );
}

export function SignalCard({ buy, sell }: { buy: string; sell: string }) {
  return (
    <section className="card">
      <h2>Buy and sell signals</h2>
      <p>Buy {buy}</p>
      <p>Sell {sell}</p>
    </section>
  );
}

export function FeeCard({ text }: { text: string }) {
  return (
    <section className="card">
      <h2>Fees</h2>
      <p>{text}</p>
    </section>
  );
}

export function OrdersCard({ orders }: { orders: DeskOrder[] | null }) {
  return (
    <section className="card">
      <h2>Open orders</h2>
      {orders === null ? <p>Keine Daten</p> : orders.length === 0 ? <p>No open orders.</p> : (
        <ul>{orders.map((order) => <li key={order.order_id ?? order.client_order_id}>{order.product_id} {order.side} {order.status}</li>)}</ul>
      )}
    </section>
  );
}

export function FillsCard({ fills }: { fills: DeskFill[] | null }) {
  return (
    <section className="card">
      <h2>Trade history</h2>
      {fills === null ? <p>Keine Daten</p> : fills.length === 0 ? <p>No fills.</p> : (
        <ul>{fills.map((fill, index) => <li key={`${fill.product_id}-${index}`}>{fill.product_id} {fill.side} {fill.size} @ {fill.price} fee {fill.commission ?? "0"}</li>)}</ul>
      )}
    </section>
  );
}

export function UtilizationCard({ rows, backtest }: { rows: UtilizationVariant[] | null; backtest: string }) {
  return (
    <section className="card">
      <h2>Capital utilization</h2>
      <p>Backtest {backtest}</p>
      {rows === null ? <p>Keine Daten</p> : (
        <ul>
          {rows.map((row) => (
            <li key={row.fraction}>
              {row.fraction} notional {row.notional} fee {row.fee} slippage {row.slippage} remaining {row.remaining_balance} stop {row.stop_loss} worst {row.worst_case_loss} {row.risk_allowed ? "risk ok" : "risk blocked"}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function ActivationCard() {
  return (
    <section className="card">
      <h2>Activation</h2>
      <p>The three live flags stay off. Defaults are not filled in. Submitting this form does not arm the desk.</p>
      <form onSubmit={(event) => event.preventDefault()}>
        <label>Max loss per trade<input name="max_loss_per_trade" defaultValue="" /></label>
        <label>Max loss per day<input name="max_loss_per_day" defaultValue="" /></label>
        <label>Max total loss<input name="max_total_loss" defaultValue="" /></label>
        <label>Max deployed capital<input name="max_deployed_capital" defaultValue="" /></label>
        <label>Allowed pairs<input name="allowed_pairs" defaultValue="" /></label>
        <label>Expiry<input name="expiry" defaultValue="" /></label>
        <label>Max slippage bps<input name="max_slippage_bps" defaultValue="" /></label>
        <label>Kill switch conditions<input name="kill_switch_conditions" defaultValue="" /></label>
        <button type="submit">Review only</button>
      </form>
    </section>
  );
}

export function SessionBar({ authenticated, onLogout }: { authenticated: boolean; onLogout: () => void }) {
  if (!authenticated) {
    return null;
  }
  return (
    <section className="card">
      <h2>Session</h2>
      <button type="button" onClick={onLogout}>Log out</button>
    </section>
  );
}

export function ApprovalCard({ onApprove }: { onApprove: (clientOrderId: string) => Promise<string | null> }) {
  const [clientOrderId, setClientOrderId] = useState("");
  const [message, setMessage] = useState("Live flags stay off. A token does not send an order.");
  return (
    <section className="card">
      <h2>Per-order approval</h2>
      <p>{message}</p>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void onApprove(clientOrderId).then((token) => {
            setMessage(token ? `Token stored for ${clientOrderId}. Submit stays blocked while live flags are off.` : "Approval was not stored.");
          });
        }}
      >
        <label>
          Client order id
          <input value={clientOrderId} onChange={(event) => setClientOrderId(event.target.value)} />
        </label>
        <button type="submit">Store approval</button>
      </form>
    </section>
  );
}
