import { isAuthorized } from "../src/control_auth.js";

const REPO = "saberdz55/saberdz55-job-application-agent";
const WORKFLOW = "agent-run.yml";
const API = "https://api.github.com";
const ALLOWED_MODES = new Set(["fully_automated", "semi_automated"]);

type ControlBody = { action?: "start" | "stop"; max_applications?: number; automation_mode?: "fully_automated" | "semi_automated" };
function env(name: string): string { const value = process.env[name]; if (!value) throw new Error(`${name} is not configured`); return value; }
function json(data: unknown, status = 200): Response { return new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } }); }
async function github(path: string, init: RequestInit = {}) {
  const response = await fetch(`${API}${path}`, { ...init, headers: { Accept: "application/vnd.github+json", Authorization: `Bearer ${env("GITHUB_PAT")}`, "X-GitHub-Api-Version": "2026-03-10", "Content-Type": "application/json", ...(init.headers || {}) } });
  const text = await response.text(); if (!response.ok) throw new Error(`GitHub API ${response.status}: ${text.slice(0, 800)}`); return text ? JSON.parse(text) : null;
}
async function latestRuns(limit = 10) { return github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=${Math.min(limit, 20)}`); }
export async function GET(request: Request): Promise<Response> {
  try { if (!isAuthorized(request)) return json({ ok: false, error: "Unauthorized" }, 401); const data = await latestRuns(5); const run = data.workflow_runs?.[0]; if (!run) return json({ ok: true, status: "idle", message: "No agent runs yet." }); return json({ ok: true, status: run.status, conclusion: run.conclusion, run_id: run.id, created_at: run.created_at, updated_at: run.updated_at, url: run.html_url, branch: run.head_branch, event: run.event }); }
  catch (error) { return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500); }
}
export async function POST(request: Request): Promise<Response> {
  try {
    if (!isAuthorized(request)) return json({ ok: false, error: "Unauthorized" }, 401);
    const body = (await request.json().catch(() => ({}))) as ControlBody;
    if (body.action === "stop") { const data = await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=1`); const run = data.workflow_runs?.[0]; if (!run) return json({ ok: true, status: "idle", message: "No running agent workflow." }); await github(`/repos/${REPO}/actions/runs/${run.id}/cancel`, { method: "POST" }); return json({ ok: true, status: "cancellation_requested", run_id: run.id, url: run.html_url }); }
    if (body.action !== "start") return json({ ok: false, error: "action must be 'start' or 'stop'" }, 400);
    const requestedMax = Number(body.max_applications ?? 1); if (!Number.isInteger(requestedMax) || requestedMax < 1 || requestedMax > 20) return json({ ok: false, error: "max_applications must be an integer from 1 to 20" }, 400);
    const mode = body.automation_mode ?? "semi_automated"; if (!ALLOWED_MODES.has(mode)) return json({ ok: false, error: "Invalid automation_mode" }, 400);
    const running = await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=1`); if (running.total_count > 0) { const run = running.workflow_runs[0]; return json({ ok: true, status: "already_running", run_id: run.id, url: run.html_url }); }
    await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, { method: "POST", body: JSON.stringify({ ref: "main", inputs: { max_applications: String(requestedMax), automation_mode: mode } }) });
    return json({ ok: true, status: "queued", max_applications: requestedMax, automation_mode: mode }, 202);
  } catch (error) { return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500); }
}
