"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { EvidenceProof } from "@/components/proof/evidence-proof";
import { ProofStatus } from "@/components/proof/proof-status";
import { RunMode } from "@/components/proof/run-mode";
import { RunProof } from "@/components/proof/run-proof";
import { SourceDeck } from "@/components/proof/source-deck";
import { proofApi, ProofApiError } from "@/lib/proof-api";
import type {
  IndexHealth,
  IndexMutation,
  KnowledgeHit,
  ProofCrashDetail,
  ProofSource,
  ProofStage,
  ResearchMode,
  ResearchRun,
} from "@/lib/proof-types";

const TENANT_ID = "proof-tenant";

const INITIAL_SOURCES: ProofSource[] = [
  {
    externalId: "durable-runtime",
    title: "Durable runtime",
    text: "Long-horizon agents need durable checkpoints, idempotent effect journals, and deterministic resume after a worker crash.",
  },
  {
    externalId: "verifier-gate",
    title: "Verifier gate",
    text: "Self-improvement stays safe when training proposals are evaluated in a sealed validation set and promoted only after verifier approval.",
  },
  {
    externalId: "hybrid-retrieval",
    title: "Hybrid retrieval",
    text: "Grounded research combines exact cosine search with Tantivy BM25, reciprocal rank fusion, and content-addressed citations.",
  },
];

function classifyError(error: unknown): {
  stage: ProofStage;
  message: string;
} {
  if (error instanceof ProofApiError) {
    if (error.status === 401 || error.status === 403) {
      return {
        stage: "unauthorized",
        message:
          "Operator session required. Open this proof from an authorized loopback backend session.",
      };
    }
    const detail = isRecord(error.detail) ? error.detail : {};
    if (
      error.status === 409 ||
      detail.code === "index_contract_error" ||
      error.message.toLowerCase().includes("adaptive_retrieval")
    ) {
      return {
        stage: "offline",
        message:
          "Rust retrieval offline. Build or install the ABI3 extension, then retry native health.",
      };
    }
  }
  return {
    stage: "error",
    message:
      error instanceof Error
        ? error.message
        : "The proof stopped unexpectedly. Retry from the last durable boundary.",
  };
}

function isCrashDetail(value: unknown): value is ProofCrashDetail {
  return (
    isRecord(value) &&
    value.step === "retrieve" &&
    typeof value.effect_key === "string" &&
    typeof value.message === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function ProofConsole() {
  const [sources, setSources] = useState(INITIAL_SOURCES);
  const [results, setResults] = useState<Map<string, IndexMutation>>(new Map());
  const [health, setHealth] = useState<IndexHealth | null>(null);
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [hits, setHits] = useState<KnowledgeHit[]>([]);
  const [crash, setCrash] = useState<ProofCrashDetail | null>(null);
  const [stage, setStage] = useState<ProofStage>("loading");
  const [message, setMessage] = useState<string | null>(null);
  const [mode, setMode] = useState<ResearchMode>("deterministic");
  const operationInFlight = useRef(false);

  const loadHealth = useCallback(async () => {
    setStage("loading");
    setMessage(null);
    try {
      const nextHealth = await proofApi.getHealth();
      setHealth(nextHealth);
      setStage(nextHealth.active_generation_id ? "ready" : "empty");
    } catch (error) {
      const next = classifyError(error);
      setStage(next.stage);
      setMessage(next.message);
    }
  }, []);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  async function ingestSources() {
    if (operationInFlight.current) return;
    operationInFlight.current = true;
    setStage("ingesting");
    setMessage(null);
    try {
      const nextResults = new Map<string, IndexMutation>();
      for (const source of sources) {
        const result = await proofApi.ingestSource({
          tenantId: TENANT_ID,
          externalId: source.externalId,
          text: source.text,
        });
        nextResults.set(source.externalId, result);
      }
      setResults(nextResults);
      const nextHealth = await proofApi.getHealth();
      setHealth(nextHealth);
      setStage(nextHealth.active_generation_id ? "ready" : "empty");
    } catch (error) {
      const next = classifyError(error);
      setStage(next.stage);
      setMessage(next.message);
    } finally {
      operationInFlight.current = false;
    }
  }

  async function completeWithEvidence(completed: ResearchRun) {
    const evidence =
      mode === "live"
        ? { hits: sealedLiveHits(completed) }
        : await proofApi.search(
            TENANT_ID,
            "How do durable agent runs resume exactly once and stay grounded?",
            6
          );
    setRun(completed);
    setHits(evidence.hits);
    setStage("completed");
  }

  async function startRun() {
    if (operationInFlight.current || stage !== "ready") return;
    operationInFlight.current = true;
    setStage("running");
    setMessage(null);
    setCrash(null);
    setHits([]);
    try {
      const created = await proofApi.createRun(TENANT_ID, {
        runId: `proof-run-${Date.now().toString(36)}`,
        goal:
          mode === "live"
            ? "Produce a grounded brief on durable long-horizon agents with safe self-improvement."
            : "Demonstrate durable checkpoints and exactly-once effects using deterministic fixture adapters.",
        actionBudget: 8,
        mode,
      });
      setRun(created);
      try {
        const completed = await proofApi.executeRun(TENANT_ID, created.id, {
          workerId: "proof-crash-worker",
          injectCrashAfter: "retrieve",
          mode,
        });
        await completeWithEvidence(completed);
      } catch (error) {
        if (
          error instanceof ProofApiError &&
          error.status === 503 &&
          isCrashDetail(error.detail)
        ) {
          setCrash(error.detail);
          setRun(await proofApi.getRun(TENANT_ID, created.id));
          setStage("crashed");
          return;
        }
        throw error;
      }
    } catch (error) {
      const next = classifyError(error);
      setStage(next.stage);
      setMessage(next.message);
    } finally {
      operationInFlight.current = false;
    }
  }

  async function resumeRun() {
    if (!run || operationInFlight.current || stage !== "crashed") return;
    operationInFlight.current = true;
    setStage("resuming");
    setMessage(null);
    try {
      const completed = await proofApi.executeRun(TENANT_ID, run.id, {
        workerId: "proof-resume-worker",
        mode,
      });
      await completeWithEvidence(completed);
    } catch (error) {
      const next = classifyError(error);
      setStage(next.stage);
      setMessage(next.message);
    } finally {
      operationInFlight.current = false;
    }
  }

  const retryable = ["offline", "unauthorized", "error"].includes(stage);

  return (
    <div className="mx-auto max-w-[1500px] space-y-6">
      <header className="relative overflow-hidden rounded-2xl border-2 border-foreground bg-card px-5 py-8 shadow-[6px_6px_0_0_#1a1a1a] sm:px-8">
        <div
          aria-hidden="true"
          className="absolute -right-16 -top-20 h-64 w-64 rounded-full bg-primary/70 blur-3xl"
        />
        <p className="relative font-mono text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">
          {mode === "live"
            ? "Live agent proof · native retrieval"
            : "Durability proof · deterministic fixture"}
        </p>
        <h1 className="relative mt-3 max-w-4xl text-4xl font-black leading-[0.95] tracking-[-0.05em] sm:text-6xl">
          Crash the worker.
          <br />
          Keep the promise.
        </h1>
        <p className="relative mt-5 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">
          {mode === "live"
            ? "Live research with the configured model, tenant native retrieval, durable Python orchestration, and inspectable grounding."
            : "Durability demo with deterministic fixture adapters. Native Rust retrieval evidence is inspected separately and is not attributed to the fixture run."}
        </p>
      </header>

      <ProofStatus health={health} run={run} stage={stage} />
      <RunMode mode={mode} onChange={setMode} stage={stage} />

      {stage === "loading" && (
        <p
          className="rounded-xl border bg-card p-4 font-mono text-xs text-muted-foreground"
          role="status"
        >
          Loading native proof state…
        </p>
      )}

      {retryable && message && (
        <div
          className="flex flex-col gap-3 rounded-xl border border-destructive bg-card p-4 text-sm sm:flex-row sm:items-center sm:justify-between"
          role="alert"
        >
          <span>{message}</span>
          <button
            className="min-h-11 rounded-lg border-2 border-foreground bg-primary px-4 font-black text-primary-foreground"
            onClick={() => void loadHealth()}
            type="button"
          >
            Retry native health
          </button>
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <SourceDeck
          disabled={stage === "ingesting"}
          onChange={setSources}
          onIngest={() => void ingestSources()}
          results={results}
          sources={sources}
        />
        <RunProof
          crash={crash}
          message={retryable ? null : message}
          mode={mode}
          onResume={() => void resumeRun()}
          onStart={() => void startRun()}
          run={run}
          stage={stage}
        />
      </div>

      <EvidenceProof health={health} hits={hits} mode={mode} run={run} />
    </div>
  );
}

function sealedLiveHits(run: ResearchRun): KnowledgeHit[] {
  const validated = new Set(
    run.artifacts.verification?.evidence_citation_ids ?? []
  );
  if (!run.artifacts.verification?.passed || validated.size === 0) {
    throw new Error("Live proof has no verifier-approved citations");
  }
  const hits = run.artifacts.retrieval
    .filter(
      (chunk) => chunk.citation_id !== null && validated.has(chunk.citation_id)
    )
    .map((chunk) => {
      if (
        !chunk.citation_id ||
        !chunk.source_id ||
        !chunk.content_hash ||
        !chunk.index_version ||
        !chunk.embedding_fingerprint ||
        chunk.fusion_score == null ||
        chunk.dense_score == null ||
        chunk.lexical_score == null
      ) {
        throw new Error(
          `Sealed citation ${chunk.citation_id ?? "unknown"} lacks retrieval lineage`
        );
      }
      return {
        tenant_id: TENANT_ID,
        source_id: chunk.source_id,
        chunk_id: chunk.citation_id,
        citation_id: chunk.citation_id,
        content_hash: chunk.content_hash,
        text: chunk.text,
        fusion_score: chunk.fusion_score,
        dense_score: chunk.dense_score,
        lexical_score: chunk.lexical_score,
        dense_rank: chunk.dense_rank ?? null,
        lexical_rank: chunk.lexical_rank ?? null,
        index_version: chunk.index_version,
        embedding_fingerprint: chunk.embedding_fingerprint,
      };
    });
  if (hits.length !== validated.size) {
    throw new Error("A verifier-approved citation is missing from sealed retrieval");
  }
  return hits;
}
