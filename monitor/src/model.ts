export const REPO = "Nate8645/HYPERGROK-AI-EMPIRE";
export const BRANCH = "cursor/phase1-desk-backend-716c";
export const PULL_NUMBER = 1;
export const CURSOR_AGENT_URL = "https://cursor.com/agents/bc-7b8bc343-af58-50dd-92c2-aed176a8716c";
export const NETWORK_INTERVAL_MS = 240_000;
export const UI_TICK_MS = 90_000;

export const AGENT_ORDER = [
  ["desk_lead", "Desk Lead"],
  ["market_analyst", "Market Analyst"],
  ["research_analyst", "Research Analyst"],
  ["strategist", "Strategist"],
  ["risk_manager", "Risk Manager"],
  ["execution_trader", "Execution Trader"],
  ["trade_reviewer", "Trade Reviewer"],
] as const;

export type AgentCard = {
  key: string;
  name: string;
  state: "Aktiv" | "Wartet" | "Fehler" | "Offline";
  task: string;
  last: string;
  completed: string;
  animate: boolean;
};

export type ChecklistItem = { id: string; label: string; done: boolean; evidence: string };

export type GithubCommit = { sha: string; message: string; at: string; url: string };
export type GithubRun = { name: string; status: string; conclusion: string | null; url: string; at: string };

export type GithubSnapshot = {
  fetchedAt: number | null;
  error: string | null;
  prState: string | null;
  prUrl: string | null;
  commits: GithubCommit[];
  files: string[];
  runs: GithubRun[];
  fromCache: boolean;
};

const EMPTY_GITHUB: GithubSnapshot = {
  fetchedAt: null,
  error: null,
  prState: null,
  prUrl: null,
  commits: [],
  files: [],
  runs: [],
  fromCache: false,
};

export function formatZurich(value: string | null | undefined): string {
  if (!value) {
    return "Keine Daten";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Keine Daten";
  }
  return new Intl.DateTimeFormat("de-CH", {
    timeZone: "Europe/Zurich",
    dateStyle: "short",
    timeStyle: "medium",
  }).format(date);
}

export function backtestLines(summary: { available?: boolean; products?: Record<string, { start?: string; end?: string; test_expectancy?: Record<string, string>; overfit_warning?: Record<string, string | null> }> } | null): string[] {
  if (!summary?.available || !summary.products) {
    return ["Keine Daten"];
  }
  return Object.entries(summary.products).map(([product, body]) => {
    const warnings = Object.entries(body.overfit_warning ?? {})
      .filter(([, warning]) => warning)
      .map(([name, warning]) => `${name}:${warning}`)
      .join(", ");
    return `${product} ${body.start ?? "Keine Daten"} bis ${body.end ?? "Keine Daten"}${warnings ? ` Warnung ${warnings}` : ""}`;
  });
}

export function checklistProgress(items: ChecklistItem[]): { done: number; total: number } {
  return { done: items.filter((item) => item.done).length, total: items.length };
}

export function mapAgents(remote: { key: string; status?: string; last_summary?: string | null; updated_at?: string | null }[] | null): AgentCard[] {
  return AGENT_ORDER.map(([key, name]) => {
    if (!remote) {
      return { key, name, state: "Offline", task: "Keine Daten", last: "Keine Daten", completed: "Keine Daten", animate: false };
    }
    const row = remote.find((item) => item.key === key);
    if (!row) {
      return { key, name, state: "Offline", task: "Keine Daten", last: "Keine Daten", completed: "Keine Daten", animate: false };
    }
    const status = (row.status || "").toLowerCase();
    let state: AgentCard["state"] = "Wartet";
    if (["error", "rejected", "reject"].includes(status)) {
      state = "Fehler";
    } else if (status === "running") {
      state = "Aktiv";
    }
    return {
      key,
      name,
      state,
      task: row.last_summary?.trim() || "Keine Daten",
      last: formatZurich(row.updated_at),
      completed: "Keine Daten",
      animate: state === "Aktiv",
    };
  });
}

type FetchLike = (url: string, init?: RequestInit) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

export async function loadGithub(fetchImpl: FetchLike, cache: GithubSnapshot | null, now: number): Promise<GithubSnapshot> {
  if (cache?.fetchedAt && now - cache.fetchedAt < NETWORK_INTERVAL_MS && !cache.error) {
    return { ...cache, fromCache: true };
  }
  const headers = { Accept: "application/vnd.github+json", "User-Agent": "hypergrok-live-control" };
  const base = `https://api.github.com/repos/${REPO}`;
  try {
    const [prRes, commitRes, runRes] = await Promise.all([
      fetchImpl(`${base}/pulls/${PULL_NUMBER}`, { headers }),
      fetchImpl(`${base}/commits?sha=${BRANCH}&per_page=5`, { headers }),
      fetchImpl(`${base}/actions/runs?per_page=5`, { headers }),
    ]);
    if ([prRes.status, commitRes.status, runRes.status].includes(403) || [prRes.status, commitRes.status, runRes.status].includes(429)) {
      return { ...(cache ?? EMPTY_GITHUB), error: "rate_limit", fromCache: Boolean(cache), fetchedAt: cache?.fetchedAt ?? null };
    }
    if (!prRes.ok || !commitRes.ok || !runRes.ok) {
      return { ...(cache ?? EMPTY_GITHUB), error: "github_error", fromCache: Boolean(cache), fetchedAt: cache?.fetchedAt ?? null };
    }
    const pr = (await prRes.json()) as { state?: string; html_url?: string };
    const commits = (await commitRes.json()) as { sha?: string; html_url?: string; commit?: { message?: string; author?: { date?: string } } }[];
    const runs = (await runRes.json()) as { workflow_runs?: { name?: string; status?: string; conclusion?: string | null; html_url?: string; updated_at?: string; head_branch?: string }[] };
    const latest = Array.isArray(commits) ? commits[0] : undefined;
    let files: string[] = [];
    if (latest?.sha) {
      const fileRes = await fetchImpl(`${base}/commits/${latest.sha}`, { headers });
      if (fileRes.status === 403 || fileRes.status === 429) {
        return { ...(cache ?? EMPTY_GITHUB), error: "rate_limit", fromCache: Boolean(cache), fetchedAt: cache?.fetchedAt ?? null };
      }
      if (fileRes.ok) {
        const detail = (await fileRes.json()) as { files?: { filename?: string }[] };
        files = (detail.files ?? []).map((file) => file.filename).filter((name): name is string => Boolean(name));
      }
    }
    return {
      fetchedAt: now,
      error: null,
      prState: pr.state ?? null,
      prUrl: pr.html_url ?? null,
      commits: (Array.isArray(commits) ? commits : []).map((item) => ({
        sha: (item.sha ?? "").slice(0, 7),
        message: item.commit?.message?.split("\n")[0] || "Keine Daten",
        at: item.commit?.author?.date || "",
        url: item.html_url || "",
      })),
      files,
      runs: (runs.workflow_runs ?? [])
        .filter((run) => !run.head_branch || run.head_branch === BRANCH || run.head_branch === "main")
        .map((run) => ({
          name: run.name || "workflow",
          status: run.status || "Keine Daten",
          conclusion: run.conclusion ?? null,
          url: run.html_url || "",
          at: run.updated_at || "",
        })),
      fromCache: false,
    };
  } catch {
    return { ...(cache ?? EMPTY_GITHUB), error: "github_error", fromCache: Boolean(cache), fetchedAt: cache?.fetchedAt ?? null };
  }
}
