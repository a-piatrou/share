/**
 * GHOSTWIRE typed API client.
 * All requests are validated client-side against the Zod schemas that mirror
 * the frozen OpenAPI contract (system/contracts/openapi.yaml, contract_version 1).
 *
 * Authentication:
 *  - /chat/query  → no auth (public endpoint, security: [])
 *  - /feedback/analyze, /team/assemble → Bearer token required (RBAC-protected)
 */
import {
  RAGAnswerSchema,
  FeedbackAnalysisSchema,
  TeamAssemblySchema,
  HealthSchema,
  type ChatQueryRequest,
  type FeedbackAnalyzeRequest,
  type TeamAssembleRequest,
  type RAGAnswer,
  type FeedbackAnalysis,
  type TeamAssembly,
  type Health,
} from "./schemas";
import type { ZodSchema } from "zod";

const BASE_URL = "";  // Vite proxy rewrites /chat, /feedback, /team, /health → localhost:8000

class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  method: "GET" | "POST",
  path: string,
  schema: ZodSchema<T>,
  options: {
    body?: unknown;
    token?: string;
  } = {},
): Promise<{ data: T; traceId: string | null }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (options.token) {
    headers["Authorization"] = `Bearer ${options.token}`;
  }

  const res = await fetch(`${BASE_URL}${path}`, {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  const traceId = res.headers.get("X-Trace-Id");

  if (!res.ok) {
    let detail = "";
    try {
      const errBody = await res.json();
      detail = errBody?.detail ?? "";
    } catch {
      // ignore parse failure
    }
    throw new ApiError(res.status, `HTTP ${res.status}: ${res.statusText}`, detail);
  }

  const raw = await res.json();

  // Client-side contract validation — fail fast on shape mismatch
  const parsed = schema.safeParse(raw);
  if (!parsed.success) {
    console.error("[GHOSTWIRE] Response failed Zod validation", parsed.error.issues);
    throw new ApiError(0, "Response shape did not match contract", JSON.stringify(parsed.error.issues));
  }

  return { data: parsed.data, traceId };
}

// ── Public endpoints (no auth) ───────────────────────────────────────────────

export async function postChatQuery(
  body: ChatQueryRequest,
): Promise<{ data: RAGAnswer; traceId: string | null }> {
  return request("POST", "/chat/query", RAGAnswerSchema, { body });
}

export async function getHealth(): Promise<Health> {
  const { data } = await request("GET", "/health", HealthSchema);
  return data;
}

// ── Internal endpoints (RBAC — bearer token required) ───────────────────────

export async function postFeedbackAnalyze(
  body: FeedbackAnalyzeRequest,
  token: string,
): Promise<{ data: FeedbackAnalysis; traceId: string | null }> {
  return request("POST", "/feedback/analyze", FeedbackAnalysisSchema, { body, token });
}

export async function postTeamAssemble(
  body: TeamAssembleRequest,
  token: string,
): Promise<{ data: TeamAssembly; traceId: string | null }> {
  return request("POST", "/team/assemble", TeamAssemblySchema, { body, token });
}

export { ApiError };
