import { Sandbox } from "@vercel/sandbox";

const REPO = "https://github.com/saberdz55/saberdz55-job-application-agent.git";
const SANDBOX_NAME = "job-agent-runner";

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
  return request.headers.get("authorization") === `Bearer ${env("MCP_AUTH_TOKEN")}`;
}

function sandboxConfig() {
  return {
    name: SANDBOX_NAME,
    runtime: "python3.13" as const,
    timeout: 45 * 60 * 1000,
    token: env("VERCEL_TOKEN"),
    teamId: env("VERCEL_TEAM_ID"),
    projectId: env("VERCEL_PROJECT_ID"),
    resources: { vcpus: 2 },
  };
}

export async function GET(request: Request): Promise<Response> {
  try {
    if (!authorized(request)) return json({ error: "Unauthorized" }, 401);
    const sandbox = await Sandbox.get({
      name: SANDBOX_NAME,
      token: env("VERCEL_TOKEN"),
      teamId: env("VERCEL_TEAM_ID"),
      projectId: env("VERCEL_PROJECT_ID"),
    });
    const check = await sandbox.runCommand({ cmd: "bash", args: ["-lc", "pgrep -af 'scripts/run_agent.py' || true"] });
    const running = check.stdout.includes("scripts/run_agent.py");
    return json({ ok: true, status: running ? "running" : "idle", sandbox_id: sandbox.sandboxId });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    if (message.toLowerCase().includes("not found")) return json({ ok: true, status: "idle" });
    return json({ ok: false, error: message }, 500);
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    if (!authorized(request)) return json({ error: "Unauthorized" }, 401);
    const body = (await request.json().catch(() => ({}))) as {
      action?: "start" | "stop";
      max_applications?: number;
      automation_mode?: "fully_automated" | "semi_automated";
    };

    if (body.action === "stop") {
      const sandbox = await Sandbox.get({
        name: SANDBOX_NAME,
        token: env("VERCEL_TOKEN"),
        teamId: env("VERCEL_TEAM_ID"),
        projectId: env("VERCEL_PROJECT_ID"),
      });
      await sandbox.stop();
      return json({ ok: true, status: "stopped" });
    }

    if (body.action !== "start") return json({ ok: false, error: "action must be start or stop" }, 400);

    const max = Math.min(Math.max(Number(body.max_applications ?? 1), 1), 20);
    const mode = body.automation_mode ?? "semi_automated";
    let sandbox: Sandbox;
    try {
      sandbox = await Sandbox.get({
        name: SANDBOX_NAME,
        token: env("VERCEL_TOKEN"),
        teamId: env("VERCEL_TEAM_ID"),
        projectId: env("VERCEL_PROJECT_ID"),
      });
      const check = await sandbox.runCommand({ cmd: "bash", args: ["-lc", "pgrep -af 'scripts/run_agent.py' || true"] });
      if (check.stdout.includes("scripts/run_agent.py")) return json({ ok: true, status: "already_running", sandbox_id: sandbox.sandboxId });
    } catch {
      sandbox = await Sandbox.create({ source: { type: "git", url: REPO }, ...sandboxConfig() });
    }

    await sandbox.runCommand({ cmd: "pip", args: ["install", "-r", "requirements.txt"], cwd: "saberdz55-job-application-agent" });
    await sandbox.runCommand({ cmd: "python", args: ["-m", "playwright", "install", "chromium"], cwd: "saberdz55-job-application-agent" });
    await sandbox.runCommand({
      cmd: "python",
      args: ["scripts/run_agent.py"],
      cwd: "saberdz55-job-application-agent",
      detached: true,
      env: {
        GEMINI_API_KEY: env("GEMINI_API_KEY"),
        ENCRYPTION_KEY: env("ENCRYPTION_KEY"),
        USER_PROFILE_JSON: env("USER_PROFILE_JSON"),
        RESUME_TEXT: env("RESUME_TEXT"),
        MAX_APPLICATIONS: String(max),
        AUTOMATION_MODE: mode,
      },
    });

    return json({ ok: true, status: "started", sandbox_id: sandbox.sandboxId, max_applications: max, automation_mode: mode }, 202);
  } catch (error) {
    return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500);
  }
}

export async function OPTIONS(): Promise<Response> {
  return new Response(null, { status: 204, headers: { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization, content-type", "access-control-allow-methods": "GET, POST, OPTIONS" } });
}
