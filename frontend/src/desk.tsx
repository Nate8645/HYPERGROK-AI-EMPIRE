import type { AgentStatus, Balance, CoinbaseStatus, JournalEntry, Portfolio, RiskConfig } from "./types";

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
