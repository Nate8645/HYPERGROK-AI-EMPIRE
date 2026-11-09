import { render, screen } from "@testing-library/react";
import { AgentBoard, BalanceCard, LiveStatus, PnlCard } from "./desk";
import { stripSecrets } from "./secrets";

test("strips secret-like fields before render", () => {
  const cleaned = stripSecrets({
    configured: false,
    coinbase_api_private_key: "should-not-render",
    nested: { api_key: "nope", symbol: "BTC-USD" },
  }) as { configured: boolean; nested: { symbol: string } };
  expect(cleaned.configured).toBe(false);
  expect(JSON.stringify(cleaned)).not.toContain("should-not-render");
  expect(JSON.stringify(cleaned)).not.toContain("nope");
  expect(cleaned.nested.symbol).toBe("BTC-USD");
});

test("shows live trading disabled and the missing prerequisites", () => {
  render(
    <LiveStatus
      status={{
        configured: false,
        live_enabled: false,
        live_armed: false,
        implementation: "rule_based",
        prerequisites: [
          { id: "credentials", ok: false, detail: "CDP API key is not configured" },
          { id: "live_trading_enabled", ok: false, detail: "LIVE_TRADING_ENABLED" },
        ],
      }}
    />,
  );
  expect(screen.getByText("DISABLED")).toBeInTheDocument();
  expect(screen.getByText("CDP API key is not configured")).toBeInTheDocument();
  expect(screen.getByText(/rule-based/i)).toBeInTheDocument();
});

test("labels every agent rule-based", () => {
  render(
    <AgentBoard
      agents={[
        { key: "desk_lead", name: "Desk Lead", mode: "rule_based", status: "idle", last_summary: null },
        { key: "risk_manager", name: "Risk Manager", mode: "rule_based", status: "idle", last_summary: null },
      ]}
    />,
  );
  expect(screen.getAllByText("rule-based")).toHaveLength(2);
});

test("balance card distinguishes not configured and empty", () => {
  const { rerender } = render(<BalanceCard state="missing" balance={null} />);
  expect(screen.getByText("not configured")).toBeInTheDocument();
  rerender(<BalanceCard state="ready" balance={{ account_state: "empty", accounts: [{ currency: "USD", available: "0" }] }} />);
  expect(screen.getByText("empty")).toBeInTheDocument();
});

test("pnl card shows realized, unrealized, and a missing mark", () => {
  render(
    <PnlCard
      portfolio={{
        positions: [
          {
            product_id: "BTC-USD",
            quantity: "1",
            cost_basis: "101",
            realized_pnl: "0",
            unrealized_pnl: null,
            fees: "1",
            mark_price: null,
          },
        ],
        realized_pnl: "0",
        unrealized_pnl: null,
        total_pnl: null,
        fees: "1",
        fees_included: true,
      }}
    />,
  );
  expect(screen.getByText(/Realized 0/)).toBeInTheDocument();
  expect(screen.getAllByText(/mark unavailable/).length).toBeGreaterThan(0);
  expect(screen.getByText(/BTC-USD/)).toBeInTheDocument();
});
