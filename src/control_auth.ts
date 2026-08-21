import { createHmac, timingSafeEqual } from "node:crypto";

const COOKIE_NAME = "job_agent_session";
const SESSION_TTL_SECONDS = 60 * 60 * 24 * 7;

function configuredToken(): string {
  const token = (process.env.JOB_AGENT_CONTROL_TOKEN || process.env.MCP_AUTH_TOKEN || "").trim();
  if (!token) throw new Error("JOB_AGENT_CONTROL_TOKEN (or MCP_AUTH_TOKEN) is not configured");
  return token;
}

function sign(payload: string): string {
  return createHmac("sha256", configuredToken()).update(payload).digest("base64url");
}

function constantTimeEqual(a: string, b: string): boolean {
  const aa = Buffer.from(a);
  const bb = Buffer.from(b);
  return aa.length === bb.length && timingSafeEqual(aa, bb);
}

export function verifyLoginToken(value: string): boolean {
  try {
    return constantTimeEqual(value.trim(), configuredToken());
  } catch {
    return false;
  }
}

export function createSessionCookie(): string {
  const expires = Math.floor(Date.now() / 1000) + SESSION_TTL_SECONDS;
  const payload = String(expires);
  const value = `${payload}.${sign(payload)}`;
  return `${COOKIE_NAME}=${value}; Path=/; Max-Age=${SESSION_TTL_SECONDS}; HttpOnly; Secure; SameSite=Strict`;
}

export function clearSessionCookie(): string {
  return `${COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict`;
}

function readCookie(request: Request): string | null {
  const header = request.headers.get("cookie") || "";
  for (const part of header.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === COOKIE_NAME) return rest.join("=") || null;
  }
  return null;
}

export function isAuthorized(request: Request): boolean {
  try {
    const bearer = request.headers.get("authorization");
    if (bearer === `Bearer ${configuredToken()}`) return true;

    const cookie = readCookie(request);
    if (!cookie) return false;
    const [expires, signature] = cookie.split(".");
    if (!expires || !signature) return false;
    if (Number(expires) < Math.floor(Date.now() / 1000)) return false;
    return constantTimeEqual(signature, sign(expires));
  } catch {
    return false;
  }
}

export { COOKIE_NAME };
