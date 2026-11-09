import { backtestLines, checklistProgress, formatZurich, loadGithub, mapAgents, NETWORK_INTERVAL_MS } from "./model";

test("agents without telemetry stay offline and do not imply work", () => {
  const cards = mapAgents(null);
  expect(cards).toHaveLength(7);
  expect(cards.every((card) => card.state === "Offline")).toBe(true);
  expect(cards.every((card) => card.task === "Keine Daten")).toBe(true);
  expect(cards.every((card) => card.completed === "Keine Daten")).toBe(true);
  expect(cards.every((card) => card.animate === false)).toBe(true);
});

test("agent states come only from telemetry and the count stays unknown", () => {
  const cards = mapAgents([
    { key: "desk_lead", status: "idle", last_summary: "waiting", updated_at: "2026-11-09T18:00:00Z" },
    { key: "risk_manager", status: "rejected", last_summary: "kill switch", updated_at: "2026-11-09T18:05:00Z" },
    { key: "execution_trader", status: "running", last_summary: "dry run", updated_at: "2026-11-09T18:06:00Z" },
  ]);
  expect(cards.find((card) => card.key === "desk_lead")?.state).toBe("Wartet");
  expect(cards.find((card) => card.key === "risk_manager")?.state).toBe("Fehler");
  expect(cards.find((card) => card.key === "execution_trader")?.animate).toBe(true);
  expect(cards.find((card) => card.key === "market_analyst")?.state).toBe("Offline");
  expect(cards.every((card) => card.completed === "Keine Daten")).toBe(true);
});

test("zurich timestamps and missing values", () => {
  expect(formatZurich(null)).toBe("Keine Daten");
  expect(formatZurich("not-a-date")).toBe("Keine Daten");
  expect(formatZurich("2026-11-09T18:00:00Z")).toContain("19:00:00");
});

test("missing backtests stay Keine Daten", () => {
  expect(backtestLines(null)).toEqual(["Keine Daten"]);
  expect(backtestLines({ available: false })).toEqual(["Keine Daten"]);
});

test("checklist progress is the count of committed items", () => {
  expect(checklistProgress([{ id: "a", label: "a", done: true, evidence: "x" }, { id: "b", label: "b", done: false, evidence: "y" }])).toEqual({ done: 1, total: 2 });
});

test("github rate limit and errors do not invent commits", async () => {
  const fetchImpl = async () => ({ ok: false, status: 403, json: async () => ({ message: "rate limit" }) });
  const limited = await loadGithub(fetchImpl, null, 1_000);
  expect(limited.error).toBe("rate_limit");
  expect(limited.commits).toEqual([]);
  expect(limited.prState).toBeNull();

  const failed = await loadGithub(async () => ({ ok: false, status: 500, json: async () => ({}) }), null, 1_000);
  expect(failed.error).toBe("github_error");
  expect(failed.commits).toEqual([]);
});

test("a fresh cache is reused inside the rate-limit window", async () => {
  let calls = 0;
  const fetchImpl = async () => {
    calls += 1;
    return { ok: true, status: 200, json: async () => ({}) };
  };
  const cached = {
    fetchedAt: 10_000,
    error: null,
    prState: "open",
    prUrl: "https://example.test/pr/1",
    commits: [],
    files: [],
    runs: [],
    fromCache: false,
  };
  const result = await loadGithub(fetchImpl, cached, 10_000 + NETWORK_INTERVAL_MS - 1);
  expect(result.fromCache).toBe(true);
  expect(result.prState).toBe("open");
  expect(calls).toBe(0);
});

test("a successful github payload maps commits, files, and workflow runs", async () => {
  const fetchImpl = async (url: string) => {
    if (url.endsWith("/pulls/1")) {
      return { ok: true, status: 200, json: async () => ({ state: "open", html_url: "https://github.com/example/pull/1" }) };
    }
    if (url.includes("/commits?")) {
      return {
        ok: true,
        status: 200,
        json: async () => [{ sha: "abcdef1234567890", html_url: "https://github.com/example/commit/abc", commit: { message: "Add adapter\n\nbody", author: { date: "2026-11-09T18:00:00Z" } } }],
      };
    }
    if (url.includes("/actions/runs")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ workflow_runs: [{ name: "CI", status: "completed", conclusion: "success", html_url: "https://github.com/example/actions/1", updated_at: "2026-11-09T18:10:00Z", head_branch: "cursor/phase1-desk-backend-716c" }] }),
      };
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ files: [{ filename: "backend/hypergrok/venues/coinbase/service.py" }] }),
    };
  };
  const result = await loadGithub(fetchImpl, null, 50_000);
  expect(result.error).toBeNull();
  expect(result.prState).toBe("open");
  expect(result.commits[0]?.message).toBe("Add adapter");
  expect(result.files).toEqual(["backend/hypergrok/venues/coinbase/service.py"]);
  expect(result.runs[0]?.conclusion).toBe("success");
});
