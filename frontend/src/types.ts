export type AgentStatus = {
  key: string;
  name: string;
  mode: string;
  status: string;
  last_summary: string | null;
};

export type Prerequisite = { id: string; ok: boolean; detail: string };

export type CoinbaseStatus = {
  configured: boolean;
  live_enabled: boolean;
  live_armed: boolean;
  prerequisites: Prerequisite[];
  implementation: string;
};

export type Balance = {
  account_state?: string;
  accounts?: { currency: string; available: string }[];
};

export type Position = {
  product_id: string;
  quantity: string;
  cost_basis: string;
  realized_pnl: string;
  unrealized_pnl: string | null;
  fees: string;
  mark_price: string | null;
};

export type Portfolio = {
  positions: Position[];
  realized_pnl: string;
  unrealized_pnl: string | null;
  total_pnl: string | null;
  fees: string;
  fees_included: boolean;
};

export type JournalEntry = { id: number; symbol: string; outcome: string; summary: string };

export type RiskConfig = {
  max_planned_risk_fraction: string;
  max_daily_loss_fraction: string;
  max_open_positions: number;
  max_new_entries_per_day: number;
  live_trading_enabled: boolean;
};
