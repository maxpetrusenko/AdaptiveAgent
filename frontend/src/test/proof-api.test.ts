import { afterEach, describe, expect, it, vi } from "vitest";

import { proofApi } from "@/lib/proof-api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("proofApi", () => {
  it("uses the real knowledge and tenant-scoped research contracts", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            generation_id: "generation-1",
            source_id: "source-1",
            index_version: "index-1",
            changed: true,
            chunk_count: 1,
          }),
          { status: 201 }
        )
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "run-1", status: "active" }), {
          status: 201,
        })
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "run-1", status: "completed" }), {
          status: 200,
        })
      );
    vi.stubGlobal("fetch", fetchMock);

    await proofApi.ingestSource({
      tenantId: "proof-tenant",
      externalId: "architecture",
      text: "Durable checkpoints survive process restarts.",
    });
    await proofApi.createRun("proof-tenant", {
      runId: "run-1",
      goal: "Prove durable retrieval",
      actionBudget: 8,
      mode: "live",
    });
    await proofApi.executeRun("proof-tenant", "run-1", {
      workerId: "proof-worker",
      injectCrashAfter: "retrieve",
      mode: "live",
    });

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/proof/knowledge/ingest",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          tenant_id: "proof-tenant",
          external_id: "architecture",
          text: "Durable checkpoints survive process restarts.",
        }),
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/proof/research/proof-tenant/runs",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          run_id: "run-1",
          goal: "Prove durable retrieval",
          action_budget: 8,
          mode: "live",
        }),
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "/api/proof/research/proof-tenant/runs/run-1/run",
      expect.objectContaining({
        body: JSON.stringify({
          worker_id: "proof-worker",
          inject_crash_after: "retrieve",
          mode: "live",
        }),
      })
    );
  });

  it("preserves status and structured detail for offline and auth states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail: {
              code: "index_contract_error",
              message: "adaptive_retrieval unavailable",
            },
          }),
          { status: 409 }
        )
      )
    );

    await expect(proofApi.getHealth()).rejects.toMatchObject({
      status: 409,
      detail: {
        code: "index_contract_error",
        message: "adaptive_retrieval unavailable",
      },
    });
  });
});
