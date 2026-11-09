import { useEffect, useState } from "react";
import { AgentBoard, BalanceCard, JournalCard, KillSwitch, LiveStatus, PnlCard, PreviewCard, PriceCard, RiskCard } from "./desk";
import { stripSecrets } from "./secrets";
import type { AgentStatus, Balance, CoinbaseStatus, JournalEntry, Portfolio, RiskConfig } from "./types";

async function readJson<T>(path: string): Promise<T | null> {
  const response = await fetch(path);
  if (!response.ok) {
    return null;
  }
  return stripSecrets(await response.json()) as T;
}

export function App() {
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [coinbase, setCoinbase] = useState<CoinbaseStatus | null>(null);
  const [balanceState, setBalanceState] = useState<"loading" | "missing" | "ready">("loading");
  const [balance, setBalance] = useState<Balance | null>(null);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [risk, setRisk] = useState<RiskConfig | null>(null);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [engaged, setEngaged] = useState(false);
  const [bid, setBid] = useState<string | null>(null);
  const [ask, setAsk] = useState<string | null>(null);
  const [source, setSource] = useState<string | null>(null);
  const [preview, setPreview] = useState("Preview is read-only until Coinbase is configured.");

  useEffect(() => {
    void readJson<{ agents: AgentStatus[] }>("/api/agents/status").then((body) => setAgents(body?.agents ?? []));
    void readJson<CoinbaseStatus>("/api/coinbase/status").then((body) => setCoinbase(body));
    void readJson<RiskConfig>("/api/risk/config").then((body) => setRisk(body));
    void readJson<{ entries: JournalEntry[] }>("/api/journal").then((body) => setJournal(body?.entries ?? []));
    void readJson<{ engaged: boolean }>("/api/risk/kill-switch").then((body) => setEngaged(Boolean(body?.engaged)));
    void (async () => {
      const response = await fetch("/api/coinbase/balances");
      if (response.status === 409) {
        setBalanceState("missing");
        return;
      }
      if (!response.ok) {
        setBalanceState("missing");
        return;
      }
      setBalance(stripSecrets(await response.json()) as Balance);
      setBalanceState("ready");
    })();
    void readJson<Portfolio>("/api/coinbase/portfolio").then((body) => setPortfolio(body));
    void (async () => {
      const response = await fetch("/api/coinbase/markets/BTC-USD/book");
      if (!response.ok) {
        return;
      }
      const body = stripSecrets(await response.json()) as { books?: { best_bid?: string; best_ask?: string; source?: string }[] };
      const book = body.books?.[0];
      setBid(book?.best_bid ?? null);
      setAsk(book?.best_ask ?? null);
      setSource(book?.source ?? null);
    })();
    const socket = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(String(event.data)) as { type?: string; payload?: { engaged?: boolean } };
      if (payload.type === "kill_switch" && payload.payload) {
        setEngaged(Boolean(payload.payload.engaged));
      }
    };
    return () => socket.close();
  }, []);

  async function toggleKill(next: boolean) {
    const response = await fetch("/api/risk/kill-switch", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ engaged: next, reason: next ? "desk halt" : "resume", updated_by: "dashboard" }),
    });
    if (response.ok) {
      const body = (await response.json()) as { engaged: boolean };
      setEngaged(body.engaged);
    }
  }

  return (
    <main>
      <header>
        <h1>HYPERGROK</h1>
        <p>Phase 2 spot desk. Rule-based agents. No secrets on this screen.</p>
      </header>
      <div className="grid">
        <LiveStatus status={coinbase} />
        <KillSwitch engaged={engaged} onToggle={(next) => void toggleKill(next)} />
        <PriceCard bid={bid} ask={ask} source={source} />
        <BalanceCard state={balanceState} balance={balance} />
        <PnlCard portfolio={portfolio} />
        <RiskCard config={risk} />
        <AgentBoard agents={agents} />
        <JournalCard entries={journal} />
        <PreviewCard message={preview} />
      </div>
    </main>
  );
}
