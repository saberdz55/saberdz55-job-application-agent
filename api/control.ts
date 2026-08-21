const REPO = "saberdz55/saberdz55-job-application-agent";
const WORKFLOW = "agent-run.yml";
const API = "https://api.github.com";

type ControlBody = {
  action?: "start" | "stop";
  max_applications?: number;
  automation_mode?: "fully_automated" | "semi_automated";
};

function env(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not configured`);
  return value;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization, content-type",
      "access-control-allow-methods": "GET, POST, OPTIONS",
    },
  });
}

function authorized(request: Request): boolean {
  const expected = env("MCP_AUTH_TOKEN");
  return request.headers.get("authorization") === `Bearer ${expected}`;
}

async function github(path: string, init: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env("GITHUB_PAT")}`,
      "X-GitHub-Api-Version": "2026-03-10",
      "Content-Type": "application/json",
      ...(init.headers || {}),
    },
  });

  const text = await response.text();
  if (!response.ok) {
    throw new Error(`GitHub API ${response.status}: ${text.slice(0, 800)}`);
  }
  return text ? JSON.parse(text) : null;
}

async function latestRuns() {
  return github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=5`);
}

export async function GET(request: Request): Promise<Response> {
  try {
    if (!authorized(request)) return json({ error: "Unauthorized" }, 401);

    const data = await latestRuns();
    const run = data.workflow_runs?.[0];
    if (!run) return json({ ok: true, status: "idle", message: "No agent runs yet." });

    return json({
      ok: true,
      status: run.status,
      conclusion: run.conclusion,
      run_id: run.id,
      created_at: run.created_at,
      updated_at: run.updated_at,
      url: run.html_url,
    });
  } catch (error) {
    return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500);
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    if (!authorized(request)) return json({ error: "Unauthorized" }, 401);

    const body = (await request.json().catch(() => ({}))) as ControlBody;
    const action = body.action;

    if (action === "stop") {
      const data = await github(
        `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=1`,
      );
      const run = data.workflow_runs?.[0];
      if (!run) return json({ ok: true, status: "idle", message: "No running agent workflow." });

      await github(`/repos/${REPO}/actions/runs/${run.id}/cancel`, { method: "POST" });
      return json({ ok: true, status: "cancellation_requested", run_id: run.id, url: run.html_url });
    }

    if (action !== "start") {
      return json({ ok: false, error: "action must be 'start' or 'stop'" }, 400);
    }

    const max = Math.min(Math.max(Number(body.max_applications ?? 10), 1), 20);
    const mode = body.automation_mode ?? "semi_automated";

    const running = await github(
      `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=1`,
    );
    if (running.total_count > 0) {
      const run = running.workflow_runs[0];
      return json({ ok: true, status: "already_running", run_id: run.id, url: run.html_url });
    }

    await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      body: JSON.stringify({
        ref: "main",
        inputs: {
          max_applications: String(max),
          automation_mode: mode,
        },
      }),
    });

    return json({
      ok: true,
      status: "queued",
      max_applications: max,
      automation_mode: mode,
      message: "Workflow dispatch accepted. Poll GET /api/control for the run status.",
    }, 202);
  } catch (error) {
    return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500);
  }
}

export async function OPTIONS(): Promise<Response> {
  return new Response(null, {
    status: 204,
    headers: {
      "access-control-allow-origin": "*",
      "access-control-allow-headers": "authorization, content-type",
      "access-control-allow-methods": "GET, POST, OPTIONS",
    },
  });
}
