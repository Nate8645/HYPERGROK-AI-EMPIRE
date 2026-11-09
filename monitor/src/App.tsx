import { useEffect, useState } from "react";
import backtestsFile from "./backtests.json";
import statusFile from "./status.json";
import {
  CURSOR_AGENT_URL,
  type AgentCard,
  type ChecklistItem,
  type GithubSnapshot,
  UI_TICK_MS,
  checklistProgress,
  backtestLines,
  loadGithub,
  loadPublicTicker,
  mapAgents,
  mapDesk,
  formatZurich,
} from "./model";

const BACKEND = import.meta.env.VITE_BACKEND_URL || "";
const ITEMS = statusFile.items as ChecklistItem[];

export function App() {
  const [github, setGithub] = useState<GithubSnapshot | null>(null);
  const [agents, setAgents] = useState<AgentCard[]>(mapAgents(null));
  const [backendNote, setBackendNote] = useState(BACKEND ? "Backend wird gelesen." : "Backend nicht verbunden");
  const [feed, setFeed] = useState<{ id: string; text: string; at: string }[]>([]);
  const [ticker, setTicker] = useState<string>("Keine Daten");
  const [desk, setDesk] = useState(mapDesk(null));

  useEffect(() => {
    let cache: GithubSnapshot | null = null;
    let stop = false;
    const tick = async () => {
      const next = await loadGithub(fetch, cache, Date.now());
      if (stop) {
        return;
      }
      cache = next;
      setGithub(next);
    };
    void tick();
    void loadPublicTicker(fetch).then((quote) => {
      if (!stop) {
        setTicker(quote ? `${quote.product} ${quote.price} (${formatZurich(quote.time)})` : "Keine Daten");
      }
    });
    const timer = window.setInterval(() => void tick(), UI_TICK_MS);
    return () => {
      stop = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!BACKEND) {
      setAgents(mapAgents(null));
      setBackendNote("Backend nicht verbunden");
      return;
    }
    let socket: WebSocket | null = null;
    const load = async () => {
      try {
        const response = await fetch(`${BACKEND}/api/agents/status`);
        if (!response.ok) {
          setAgents(mapAgents(null));
          setBackendNote("Backend nicht verbunden");
          return;
        }
        const body = (await response.json()) as { agents?: { key: string; status?: string; last_summary?: string | null; updated_at?: string | null }[] };
        setAgents(mapAgents(body.agents ?? []));
        setBackendNote("Backend verbunden");
        const [riskRes, journalRes, coinbaseRes] = await Promise.all([
          fetch(`${BACKEND}/api/risk/config`),
          fetch(`${BACKEND}/api/journal`),
          fetch(`${BACKEND}/api/coinbase/status`),
        ]);
        setDesk(mapDesk({
          configured: true,
          risk: riskRes.ok ? await riskRes.json() : null,
          journal: journalRes.ok ? ((await journalRes.json()) as { entries?: { outcome?: string; symbol?: string; summary?: string }[] }).entries ?? [] : null,
          coinbase: coinbaseRes.ok ? await coinbaseRes.json() : null,
        }));
      } catch {
        setAgents(mapAgents(null));
        setBackendNote("Backend nicht verbunden");
      }
    };
    void load();
    try {
      const url = new URL(BACKEND);
      url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
      url.pathname = "/ws/events";
      socket = new WebSocket(url.toString());
      socket.onmessage = (event) => {
        const payload = JSON.parse(String(event.data)) as { type?: string; summary?: string; at?: string };
        if (!payload.type || payload.type === "ws.connected") {
          return;
        }
        setFeed((current) => [{ id: `${payload.at ?? ""}-${current.length}`, text: payload.summary || payload.type || "Keine Daten", at: payload.at || "" }, ...current].slice(0, 12));
      };
    } catch {
      setBackendNote("Backend nicht verbunden");
    }
    return () => socket?.close();
  }, []);

  const progress = checklistProgress(ITEMS);
  const ci = github?.runs[0];

  return (
    <main>
      <header>
        <p className="kicker">READ ONLY</p>
        <h1>HYPERGROK LIVE CONTROL</h1>
        <p>Öffentliche Repo-Daten und, falls konfiguriert, Desk-Telemetrie. Keine Orders, kein Kill-Switch, keine Schlüssel.</p>
      </header>
      <section className="progress card">
        <h2>Checklist</h2>
        <p>{progress.total === 0 ? "Keine Daten" : `${progress.done} von ${progress.total}`}</p>
        <div className="bar" aria-hidden="true"><span style={{ width: progress.total ? `${(progress.done / progress.total) * 100}%` : "0%" }} /></div>
        <ul>
          {ITEMS.map((item) => (
            <li key={item.id}>{item.done ? "erledigt" : "offen"} — {item.label} ({item.evidence})</li>
          ))}
        </ul>
      </section>
      <section className="grid">
        <article className="card">
          <h2>Pull Request</h2>
          <p>{github?.error === "rate_limit" ? "GitHub Rate-Limit. Cache bleibt, nichts wird erfunden." : github?.prState ?? "Keine Daten"}</p>
          {github?.prUrl ? <a href={github.prUrl}>PR #{1}</a> : null}
          <p>{github?.fetchedAt ? formatZurich(new Date(github.fetchedAt).toISOString()) : "Keine Daten"}</p>
        </article>
        <article className="card">
          <h2>CI</h2>
          <p>{ci ? `${ci.name}: ${ci.status}${ci.conclusion ? ` / ${ci.conclusion}` : ""}` : "Keine Daten"}</p>
          {ci?.url ? <a href={ci.url}>Workflow</a> : null}
        </article>
        <article className="card">
          <h2>Cursor Agent</h2>
          <p>Nicht verfügbar</p>
          <a href={CURSOR_AGENT_URL}>Agent öffnen</a>
        </article>
        <article className="card">
          <h2>Backend</h2>
          <p>{backendNote}</p>
        </article>
        <article className="card">
          <h2>Coinbase Markt</h2>
          <p>{ticker}</p>
        </article>
        <article className="card">
          <h2>Ideen und Risiko</h2>
          <p>{desk.ideas}</p>
          <p>{desk.risk}</p>
          <p>{desk.proposals}</p>
        </article>
      </section>
      <section className="agents">
        {agents.map((agent) => (
          <article key={agent.key} className={agent.animate ? "card live" : "card"}>
            <h2>{agent.name}</h2>
            <p className="tag">rule-based</p>
            <p>{agent.state}</p>
            <p>{agent.task}</p>
            <p>{agent.last}</p>
            <p>Abgeschlossen: {agent.completed}</p>
          </article>
        ))}
      </section>
      <section className="card">
        <h2>Commits</h2>
        {github?.commits.length ? (
          <ul>{github.commits.map((commit) => <li key={commit.sha}>{commit.sha} {commit.message} — {formatZurich(commit.at)}</li>)}</ul>
        ) : <p>Keine Daten</p>}
      </section>
      <section className="card">
        <h2>Dateien im letzten Commit</h2>
        {github?.files.length ? <ul>{github.files.map((file) => <li key={file}>{file}</li>)}</ul> : <p>Keine Daten</p>}
      </section>
      <section className="card">
        <h2>Backtests</h2>
        <ul>{backtestLines(backtestsFile).map((line) => <li key={line}>{line}</li>)}</ul>
      </section>
      <section className="card">
        <h2>Fehler und Warnungen</h2>
        <p>{github?.error === "rate_limit" ? "GitHub Rate-Limit" : github?.error === "github_error" ? "GitHub Fehler" : "Keine Daten"}</p>
      </section>
      <section className="card">
        <h2>Aktivität</h2>
        {feed.length ? <ul>{feed.map((item) => <li key={item.id}>{formatZurich(item.at)} — {item.text}</li>)}</ul> : <p>Keine Daten</p>}
      </section>
    </main>
  );
}
