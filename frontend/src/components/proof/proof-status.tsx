import { Cpu, Database, Route } from "lucide-react";

import type {
  IndexHealth,
  ProofStage,
  ResearchRun,
} from "@/lib/proof-types";

interface ProofStatusProps {
  stage: ProofStage;
  health: IndexHealth | null;
  run: ResearchRun | null;
}

export function ProofStatus({ stage, health, run }: ProofStatusProps) {
  const nativeLabel =
    stage === "offline"
      ? "Rust retrieval offline"
      : health?.active_index_version
        ? "Native index ready"
        : "Native index awaiting corpus";
  const traceLabel = run ? "Trace metadata captured" : "Trace awaiting run";
  const runLabel = run
    ? `${run.status} · ${run.actions_used}/${run.action_budget} actions`
    : "No run started";

  return (
    <section
      aria-label="Proof system status"
      aria-live="polite"
      className="grid gap-3 sm:grid-cols-3"
    >
      <StatusCell
        icon={<Cpu className="h-4 w-4" aria-hidden="true" />}
        eyebrow="Native engine"
        label={nativeLabel}
        detail={
          health?.active_index_version
            ? health.active_index_version
            : "Exact cosine · BM25 · RRF"
        }
        tone={stage === "offline" ? "danger" : health?.active_index_version ? "live" : "idle"}
      />
      <StatusCell
        icon={<Database className="h-4 w-4" aria-hidden="true" />}
        eyebrow="Evidence index"
        label={
          health?.active_generation_id
            ? `${health.chunk_count} chunks active`
            : "No active evidence index"
        }
        detail={health?.active_generation_id ?? "Ingest the three sources to begin"}
        tone={health?.active_generation_id ? "live" : "idle"}
      />
      <StatusCell
        icon={<Route className="h-4 w-4" aria-hidden="true" />}
        eyebrow={traceLabel}
        label={runLabel}
        detail={run ? `state v${run.version} · plan v${run.plan_version}` : "Durable run ledger"}
        tone={run?.status === "completed" ? "live" : "idle"}
      />
    </section>
  );
}

function StatusCell({
  icon,
  eyebrow,
  label,
  detail,
  tone,
}: {
  icon: React.ReactNode;
  eyebrow: string;
  label: string;
  detail: string;
  tone: "live" | "idle" | "danger";
}) {
  const dot =
    tone === "live"
      ? "bg-primary"
      : tone === "danger"
        ? "bg-destructive"
        : "bg-muted-foreground";
  return (
    <div className="rounded-xl border bg-card p-4">
      <p className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.16em] text-muted-foreground">
        {icon}
        {eyebrow}
      </p>
      <p className="mt-3 flex items-center gap-2 text-sm font-black">
        <span className={`h-2.5 w-2.5 rounded-full ${dot}`} aria-hidden="true" />
        {label}
      </p>
      <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
        {detail}
      </p>
    </div>
  );
}
