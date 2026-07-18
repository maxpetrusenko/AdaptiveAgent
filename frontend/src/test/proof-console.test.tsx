import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProofConsole } from "@/components/proof/proof-console";
import { ProofApiError } from "@/lib/proof-api";

const mocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  ingestSource: vi.fn(),
  createRun: vi.fn(),
  getRun: vi.fn(),
  executeRun: vi.fn(),
  search: vi.fn(),
}));

vi.mock("@/lib/proof-api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/proof-api")>();
  return {
    ...actual,
    proofApi: mocks,
  };
});

const activeRun = {
  id: "proof-run-1",
  goal: "Prove grounded durable research",
  status: "active" as const,
  cursor: 2,
  version: 2,
  plan_version: 1,
  action_budget: 8,
  actions_used: 2,
  terminal_reason: null,
  steps: [
    { name: "plan" as const, status: "completed" as const, attempt: 1 },
    { name: "retrieve" as const, status: "completed" as const, attempt: 1 },
    { name: "synthesize" as const, status: "active" as const, attempt: 1 },
    { name: "verify" as const, status: "pending" as const, attempt: 1 },
  ],
  artifacts: {
    plan: { queries: ["durable research"] },
    retrieval: [
      {
        citation_id: "chunk-a",
        text: "Checkpoint evidence",
        source_id: "source-a",
        content_hash: "sealed-hash-a",
        fusion_score: 0.032,
        dense_score: 0.98,
        lexical_score: 1.4,
        dense_rank: 1,
        lexical_rank: 1,
        index_version: "sealed-index-3",
        embedding_fingerprint: "sealed-embedding-v1",
      },
    ],
    synthesis: null,
    verification: null,
  },
};

const completedRun = {
  ...activeRun,
  status: "completed" as const,
  cursor: 4,
  version: 4,
  actions_used: 4,
  steps: activeRun.steps.map((step) => ({
    ...step,
    status: "completed" as const,
  })),
  artifacts: {
    ...activeRun.artifacts,
    synthesis: {
      answer: "The run resumed from its sealed retrieval effect.",
      citation_ids: ["chunk-a"],
    },
    verification: {
      passed: true,
      evidence_citation_ids: ["chunk-a"],
      reason: "Every claim has evidence.",
    },
  },
};

describe("ProofConsole", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mocks.getHealth
      .mockResolvedValueOnce({
        status: "empty",
        active_generation_id: null,
        active_index_version: null,
        building_count: 0,
        chunk_count: 0,
      })
      .mockResolvedValue({
        status: "ready",
        active_generation_id: "generation-3",
        active_index_version: "index-3",
        building_count: 0,
        chunk_count: 3,
      });
    mocks.ingestSource.mockResolvedValue({
      generation_id: "generation-3",
      source_id: "source-a",
      index_version: "index-3",
      changed: true,
      chunk_count: 1,
    });
    mocks.createRun.mockResolvedValue(activeRun);
    mocks.executeRun
      .mockRejectedValueOnce(
        new ProofApiError("Injected proof crash", 503, {
          message: "Injected proof crash after sealed effect",
          step: "retrieve",
          effect_key: "retrieve:proof-run-1:v1",
        })
      )
      .mockResolvedValueOnce(completedRun);
    mocks.getRun.mockResolvedValue(activeRun);
    mocks.search.mockResolvedValue({
      hits: [
        {
          tenant_id: "proof-tenant",
          source_id: "source-a",
          chunk_id: "chunk-a",
          citation_id: "chunk-a",
          content_hash: "7f9c5c3a12e8",
          text: "Checkpoint evidence",
          fusion_score: 0.032,
          dense_score: 0.98,
          lexical_score: 1.4,
          dense_rank: 1,
          lexical_rank: 1,
          index_version: "index-3",
          embedding_fingerprint: "gemini-embedding-2:768",
        },
      ],
    });
  });

  it("shows ingest, controlled crash, resume, exactly-once and citation proof", async () => {
    render(<ProofConsole />);

    expect(await screen.findByText(/No active evidence index/i)).toBeVisible();
    expect(
      screen.getByText("Deterministic fixture", { exact: true })
    ).toBeVisible();
    expect(screen.getAllByRole("button", { name: /Inspect source/i })).toHaveLength(
      3
    );

    fireEvent.click(screen.getByRole("button", { name: /Ingest 3 sources/i }));
    expect(await screen.findByText(/Native index ready/i)).toBeVisible();

    fireEvent.click(
      screen.getByRole("button", { name: /Start deterministic run/i })
    );
    expect(await screen.findByText(/Controlled crash sealed/i)).toBeVisible();
    expect(mocks.executeRun).toHaveBeenNthCalledWith(
      1,
      "proof-tenant",
      "proof-run-1",
      {
        workerId: "proof-crash-worker",
        injectCrashAfter: "retrieve",
        mode: "deterministic",
      }
    );
    expect(screen.getByText("retrieve:proof-run-1:v1")).toBeVisible();
    expect(screen.getByRole("button", { name: /Resume from checkpoint/i })).toBeEnabled();

    fireEvent.click(
      screen.getByRole("button", { name: /Resume from checkpoint/i })
    );

    expect(await screen.findByText(/Fixture verifier passed/i)).toBeVisible();
    expect(
      screen.queryByText(/Live citations verified/i)
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/separate native retrieval inspection/i)
    ).toBeVisible();
    expect(screen.getByText(/Exactly-once effect reused/i)).toBeVisible();
    expect(screen.getByText("chunk-a")).toBeVisible();
    expect(screen.getByText(/gemini-embedding-2:768/i)).toBeVisible();
    expect(screen.getByText(/Parity before latency/i)).toBeVisible();
    expect(mocks.executeRun).toHaveBeenNthCalledWith(
      2,
      "proof-tenant",
      "proof-run-1",
      { workerId: "proof-resume-worker", mode: "deterministic" }
    );
  });

  it("does not start a run while source ingestion is still in flight", async () => {
    let finishIngest: ((value: Awaited<ReturnType<typeof mocks.ingestSource>>) => void) | undefined;
    mocks.ingestSource.mockReset().mockImplementation(
      () =>
        new Promise((resolve) => {
          finishIngest = resolve;
        })
    );
    render(<ProofConsole />);
    await screen.findByText(/No active evidence index/i);

    fireEvent.click(screen.getByRole("button", { name: /Ingest 3 sources/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /Start deterministic run/i })
    );

    expect(mocks.createRun).not.toHaveBeenCalled();
    finishIngest?.({
      generation_id: "generation-3",
      source_id: "source-a",
      index_version: "index-3",
      changed: true,
      chunk_count: 1,
    });
  });

  it("sends live mode explicitly and labels live grounding honestly", async () => {
    render(<ProofConsole />);
    await screen.findByText(/No active evidence index/i);
    fireEvent.click(screen.getByRole("button", { name: /Ingest 3 sources/i }));
    await screen.findByText(/Native index ready/i);

    fireEvent.click(
      screen.getByRole("radio", { name: "Live model + native retrieval" })
    );
    expect(
      screen.getByText("Live model + native retrieval", { exact: true })
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: /Start live run/i })
    );
    await screen.findByText(/Controlled crash sealed/i);
    fireEvent.click(
      screen.getByRole("button", { name: /Resume from checkpoint/i })
    );

    expect(await screen.findByText(/Live citations verified/i)).toBeVisible();
    expect(screen.getByText("sealed-hash-a")).toBeVisible();
    expect(screen.getByText("sealed-index-3")).toBeVisible();
    expect(mocks.search).not.toHaveBeenCalled();
    expect(mocks.executeRun).toHaveBeenNthCalledWith(
      1,
      "proof-tenant",
      "proof-run-1",
      {
        workerId: "proof-crash-worker",
        injectCrashAfter: "retrieve",
        mode: "live",
      }
    );
    expect(mocks.executeRun).toHaveBeenNthCalledWith(
      2,
      "proof-tenant",
      "proof-run-1",
      { workerId: "proof-resume-worker", mode: "live" }
    );
  });

  it("renders explicit Rust-offline and unauthorized recovery states", async () => {
    mocks.getHealth.mockReset().mockRejectedValue(
      new ProofApiError("native offline", 409, {
        code: "index_contract_error",
        message: "adaptive_retrieval unavailable",
      })
    );
    const firstView = render(<ProofConsole />);
    expect(
      await screen.findByText("Rust retrieval offline", { exact: true })
    ).toBeVisible();
    firstView.unmount();

    mocks.getHealth.mockReset().mockResolvedValue({
      status: "ready",
      active_generation_id: "generation-3",
      active_index_version: "index-3",
      building_count: 0,
      chunk_count: 3,
    });
    mocks.createRun.mockRejectedValueOnce(
      new ProofApiError("unauthorized", 401, "Operator session required")
    );
    render(<ProofConsole />);
    await waitFor(() =>
      expect(screen.getByText(/Native index ready/i)).toBeVisible()
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Start deterministic run/i })
    );
    expect(await screen.findByText(/Operator session required/i)).toBeVisible();
  });
});
