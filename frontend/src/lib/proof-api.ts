import type {
  CreateResearchRunInput,
  ExecuteResearchRunInput,
  IndexHealth,
  IndexMutation,
  IngestSourceInput,
  KnowledgeSearchResponse,
  ResearchRun,
} from "@/lib/proof-types";

const API_BASE = "/api/proof";

export class ProofApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown
  ) {
    super(message);
    this.name = "ProofApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await parsePayload(response);
    const detail = isRecord(payload) && "detail" in payload ? payload.detail : payload;
    throw new ProofApiError(errorMessage(detail, response.status), response.status, detail);
  }
  return (await response.json()) as T;
}

const jsonRequest = (method: "POST", body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const tenantPath = (tenantId: string) => encodeURIComponent(tenantId);
const runPath = (runId: string) => encodeURIComponent(runId);

export const proofApi = {
  getHealth: () => request<IndexHealth>("/knowledge/index/health"),

  ingestSource: (input: IngestSourceInput) =>
    request<IndexMutation>(
      "/knowledge/ingest",
      jsonRequest("POST", {
        tenant_id: input.tenantId,
        external_id: input.externalId,
        text: input.text,
      })
    ),

  search: (tenantId: string, query: string, topK = 5) =>
    request<KnowledgeSearchResponse>(
      "/knowledge/search",
      jsonRequest("POST", {
        tenant_id: tenantId,
        query,
        top_k: topK,
      })
    ),

  createRun: (tenantId: string, input: CreateResearchRunInput) =>
    request<ResearchRun>(
      `/research/${tenantPath(tenantId)}/runs`,
      jsonRequest("POST", {
        run_id: input.runId,
        goal: input.goal,
        action_budget: input.actionBudget,
        mode: input.mode,
      })
    ),

  getRun: (tenantId: string, runId: string) =>
    request<ResearchRun>(
      `/research/${tenantPath(tenantId)}/runs/${runPath(runId)}`
    ),

  executeRun: (
    tenantId: string,
    runId: string,
    input: ExecuteResearchRunInput
  ) =>
    request<ResearchRun>(
      `/research/${tenantPath(tenantId)}/runs/${runPath(runId)}/run`,
      jsonRequest("POST", {
        worker_id: input.workerId,
        ...(input.injectCrashAfter
          ? { inject_crash_after: input.injectCrashAfter }
          : {}),
        mode: input.mode,
      })
    ),
};

async function parsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function errorMessage(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail) {
    return detail;
  }
  if (isRecord(detail) && typeof detail.message === "string") {
    return detail.message;
  }
  return `Proof API error: ${status}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
