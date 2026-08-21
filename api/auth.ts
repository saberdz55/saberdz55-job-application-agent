import { createSessionCookie, clearSessionCookie, isAuthorized, verifyLoginToken } from "../src/control_auth";

function json(data: unknown, status = 200, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store", ...headers },
  });
}

export async function POST(request: Request): Promise<Response> {
  try {
    const body = await request.json().catch(() => ({}));
    const action = body?.action;

    if (action === "logout") {
      return json({ ok: true }, 200, { "set-cookie": clearSessionCookie() });
    }

    if (action !== "login" || typeof body?.token !== "string" || !verifyLoginToken(body.token)) {
      return json({ ok: false, error: "Invalid control token" }, 401);
    }

    return json({ ok: true }, 200, { "set-cookie": createSessionCookie() });
  } catch (error) {
    return json({ ok: false, error: error instanceof Error ? error.message : "Unknown error" }, 500);
  }
}

export async function GET(request: Request): Promise<Response> {
  return json({ ok: isAuthorized(request) }, isAuthorized(request) ? 200 : 401);
}
