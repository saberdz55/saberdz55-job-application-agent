import { isAuthorized } from "../src/control_auth";

const REPO = "saberdz55/saberdz55-job-application-agent";
const WORKFLOW = "agent-run.yml";

function env(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not configured`);
  return value;
}

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

async function github(path: string) {
  const response = await fetch(`https://api.github.com${path}`, {
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env("GITHUB_PAT")}`,
      "X-GitHub-Api-Version": "2026-03-10",
    },
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`GitHub API ${response.status}: ${text.slice(0, 800)}`);
  return text ? JSON.parse(text) : null;
}

export async function GET(request: Request): Promise<Response> {
  try {
    if (!isAuthorized(request)) return json({ ok: false, error: "Unauthorized" }, 401);
    const url = new URL(request.url);
    const limit = Math.min(Math.max(Number(url.searchParams.get("limit") || 8), 1), 20);
    const data = await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=${limit}`);
    const runs = (data.workflow_runs || []).map((run: any) => ({
      id: run.id,
      status: run.status,
      conclusion: run.conclusion,
      created_at: run.created_at,
      updated_at: run.updated_at,
      url: run.html_url,
      branch: run.head_branch,
      event: run.event,
    }));
    return json({ ok: true, runs });
  } catch (error) {
    return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500);
  }
}
