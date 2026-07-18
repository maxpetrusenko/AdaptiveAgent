import {
  Check,
  Circle,
  Loader2,
  Play,
  RotateCcw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import type {
  ProofCrashDetail,
  ProofStage,
  ResearchMode,
  ResearchRun,
} from "@/lib/proof-types";

interface RunProofProps {
  stage: ProofStage;
  run: ResearchRun | null;
  crash: ProofCrashDetail | null;
  message: string | null;
  onStart: () => void;
  onResume: () => void;
  mode: ResearchMode;
}

export function RunProof({
  stage,
  run,
  crash,
  message,
  onStart,
  onResume,
  mode,
}: RunProofProps) {
  const busy = stage === "running" || stage === "resuming";
  const verification = run?.artifacts.verification;

  return (
    <section
      aria-labelledby="proof-run-heading"
      className="rounded-2xl border bg-foreground p-4 text-background shadow-[5px_5px_0_0_#c8ff00] sm:p-6"
    >
      <p className="text-xs font-black uppercase tracking-[0.22em] text-primary">
        02 · Durable execution
      </p>
      <h2 id="proof-run-heading" className="mt-1 text-2xl font-black">
        Crash it. Resume it. Inspect it.
      </h2>
      <p className="mt-2 max-w-xl text-sm text-background/65">
        {mode === "live"
          ? "The configured model and tenant native index execute this run. The first execution intentionally crashes after retrieval is sealed."
          : "Fixture adapters execute this run. It proves durable resume behavior only and does not claim live model or native retrieval grounding."}
      </p>

      {message && (
        <div
          role="alert"
          className="mt-4 rounded-lg border border-orange-300/40 bg-orange-300/10 p-3 text-sm"
        >
          {message}
        </div>
      )}

      <ol aria-label="Research checkpoints" className="mt-5 grid gap-2 sm:grid-cols-4">
        {(run?.steps ?? DEFAULT_STEPS).map((step) => (
          <li
            key={step.name}
            className="rounded-lg border border-background/20 bg-background/5 p-3"
          >
            <span className="flex items-center justify-between">
              <span className="text-xs font-black uppercase">{step.name}</span>
              {step.status === "completed" ? (
                <Check className="h-4 w-4 text-primary" aria-label="Completed" />
              ) : step.status === "active" ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary" aria-label="Active" />
              ) : (
                <Circle className="h-4 w-4 text-background/40" aria-label="Pending" />
              )}
            </span>
            <span className="mt-2 block font-mono text-[11px] text-background/55">
              attempt {step.attempt}
            </span>
          </li>
        ))}
      </ol>

      {crash && (
        <div className="mt-4 rounded-lg border border-orange-300/50 bg-orange-300/10 p-4">
          <p className="flex items-center gap-2 font-black text-orange-200">
            <TriangleAlert className="h-4 w-4" aria-hidden="true" />
            Controlled crash sealed
          </p>
          <p className="mt-2 text-sm text-background/70">
            Retrieval completed before process failure. This effect key is the
            durable replay boundary.
          </p>
          <code className="mt-2 block overflow-x-auto rounded bg-black/30 p-2 text-xs text-primary">
            {crash.effect_key}
          </code>
        </div>
      )}

      {stage === "completed" && crash && (
        <div className="mt-4 rounded-lg border border-primary/60 bg-primary/10 p-4">
          <p className="flex items-center gap-2 font-black text-primary">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            Exactly-once effect reused
          </p>
          <p className="mt-1 text-sm text-background/70">
            Retrieve remains completed at attempt 1; resume continued from
            synthesis.
          </p>
        </div>
      )}

      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        {stage !== "crashed" && stage !== "resuming" && (
          <button
            type="button"
            onClick={onStart}
            disabled={busy || stage === "empty" || stage === "loading" || stage === "offline"}
            className="flex min-h-11 items-center justify-center gap-2 rounded-lg border-2 border-primary bg-primary px-4 py-2 text-sm font-black text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:opacity-40"
          >
            {stage === "running" ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : (
              <Play className="h-4 w-4" aria-hidden="true" />
            )}
            {stage === "running"
              ? "Running to crash…"
              : mode === "live"
                ? "Start live run"
                : "Start deterministic run"}
          </button>
        )}
        {(stage === "crashed" || stage === "resuming") && (
          <button
            type="button"
            onClick={onResume}
            disabled={stage === "resuming"}
            className="flex min-h-11 items-center justify-center gap-2 rounded-lg border-2 border-primary bg-primary px-4 py-2 text-sm font-black text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-50"
          >
            <RotateCcw
              className={`h-4 w-4 ${stage === "resuming" ? "animate-spin" : ""}`}
              aria-hidden="true"
            />
            {stage === "resuming" ? "Resuming…" : "Resume from checkpoint"}
          </button>
        )}
      </div>

      <div className="mt-5 grid gap-3 border-t border-background/15 pt-4 sm:grid-cols-2">
        <ProofDatum
          label="Grounding state"
          value={
            verification?.passed
              ? mode === "live"
                ? "Live citations verified"
                : "Fixture verifier passed"
              : verification
                ? "Verification failed"
                : "Awaiting verification"
          }
        />
        <ProofDatum
          label="Trace metadata status"
          value={
            run
              ? `${run.id} · state v${run.version} · ${run.actions_used}/${run.action_budget} actions`
              : "No durable trace yet"
          }
        />
      </div>
    </section>
  );
}

const DEFAULT_STEPS = ["plan", "retrieve", "synthesize", "verify"].map(
  (name) => ({
    name,
    status: "pending" as const,
    attempt: 1,
  })
);

function ProofDatum({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-black uppercase tracking-[0.16em] text-background/45">
        {label}
      </p>
      <p className="mt-1 text-sm font-bold">{value}</p>
    </div>
  );
}
