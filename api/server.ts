import { createMcpHandler } from "mcp-handler";
import { z } from "zod";

const REPO = "saberdz55/saberdz55-job-application-agent";
const WORKFLOW = "agent-run.yml";
const GITHUB_API = "https://api.github.com";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`${name} is not configured`);
  return value;
}

async function github(path: string, init: RequestInit = {}) {
  const token = requireEnv("GITHUB_PAT");
  const response = await fetch(`${GITHUB_API}${path}`, {
    ...init,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(init.headers || {}),
    },
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`GitHub API ${response.status}: ${body.slice(0, 500)}`);
  }

  if (response.status === 204) return null;
  return response.json();
}

async function authorized(request: Request): Promise<Response | null> {
  const expected = process.env.MCP_AUTH_TOKEN;
  if (!expected) return new Response("MCP_AUTH_TOKEN is not configured", { status: 500 });

  const supplied = request.headers.get("authorization");
  if (supplied !== `Bearer ${expected}`) {
    return new Response("Unauthorized", {
      status: 401,
      headers: { "WWW-Authenticate": "Bearer" },
    });
  }
  return null;
}

const mcp = createMcpHandler((server) => {
  server.tool(
    "start_auto_apply",
    "Start the existing autonomous job-application workflow through GitHub Actions.",
    {
      max_applications: z.number().int().min(1).max(20).default(10),
      automation_mode: z.enum(["fully_automated", "semi_automated"]).default("semi_automated"),
    },
    async ({ max_applications, automation_mode }) => {
      const running = await github(
        `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=1`,
      );
      if (running.total_count > 0) {
        return {
          content: [{ type: "text", text: `Already running: ${running.workflow_runs[0].html_url}` }],
        };
      }

      await github(`/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
        method: "POST",
        body: JSON.stringify({
          ref: "main",
          inputs: {
            max_applications: String(max_applications),
            automation_mode,
          },
        }),
      });

      return {
        content: [{
          type: "text",
          text: `Started GitHub Actions workflow. max_applications=${max_applications}, automation_mode=${automation_mode}. Use get_status to monitor it.`,
        }],
      };
    },
  );

  server.tool(
    "get_status",
    "Get the latest autonomous job-agent workflow status.",
    {},
    async () => {
      const data = await github(
        `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=5`,
      );
      const run = data.workflow_runs?.[0];
      if (!run) {
        return { content: [{ type: "text", text: "No agent runs yet." }] };
      }
      return {
        content: [{
          type: "text",
          text: JSON.stringify({
            id: run.id,
            status: run.status,
            conclusion: run.conclusion,
            created_at: run.created_at,
            updated_at: run.updated_at,
            url: run.html_url,
          }),
        }],
      };
    },
  );

  server.tool(
    "get_history",
    "List recent autonomous agent workflow runs.",
    { limit: z.number().int().min(1).max(20).default(10) },
    async ({ limit }) => {
      const data = await github(
        `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=${limit}`,
      );
      const runs = (data.workflow_runs || []).map((run: any) => ({
        id: run.id,
        status: run.status,
        conclusion: run.conclusion,
        created_at: run.created_at,
        url: run.html_url,
      }));
      return { content: [{ type: "text", text: JSON.stringify(runs) }] };
    },
  );

  server.tool(
    "stop_auto_apply",
    "Cancel the latest running autonomous job-agent workflow.",
    {},
    async () => {
      const data = await github(
        `/repos/${REPO}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=1`,
      );
      const run = data.workflow_runs?.[0];
      if (!run) {
        return { content: [{ type: "text", text: "No running agent workflow." }] };
      }
      await github(`/repos/${REPO}/actions/runs/${run.id}/cancel`, { method: "POST" });
      return { content: [{ type: "text", text: `Cancellation requested for run ${run.id}.` }] };
    },
  );
});

async function handler(request: Request): Promise<Response> {
  const denial = await authorized(request);
  if (denial) return denial;
  return mcp(request);
}

export { handler as GET, handler as POST, handler as DELETE };
