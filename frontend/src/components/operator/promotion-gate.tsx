"use client";

import { ArrowRight, CheckCircle2, RotateCcw, ShieldCheck } from "lucide-react";
import { useCallback, useState } from "react";

import { ConfirmationDialog } from "@/components/operator/confirmation-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import type { PromotionCandidate } from "@/lib/operator-types";

interface PromotionGateProps {
  candidates: PromotionCandidate[];
  onPromote: (candidateId: string) => void;
  onRollback: (candidateId: string) => void;
  pendingActionIds?: ReadonlySet<string>;
}

const percent = (value: number) => `${Math.round(value * 100)}%`;
const pointDelta = (baseline: number, candidate: number) => {
  const points = Math.round((candidate - baseline) * 100);
  return `${points >= 0 ? "+" : ""}${points} pts`;
};

export function PromotionGate({
  candidates,
  onPromote,
  onRollback,
  pendingActionIds = new Set(),
}: PromotionGateProps) {
  const [selectedId, setSelectedId] = useState(candidates[0]?.id ?? null);
  const [confirmationKind, setConfirmationKind] = useState<
    "promote" | "rollback" | null
  >(null);
  const [confirmation, setConfirmation] = useState("");
  const closeConfirmation = useCallback(() => {
    setConfirmationKind(null);
    setConfirmation("");
  }, []);
  const selected =
    candidates.find((candidate) => candidate.id === selectedId) ??
    candidates[0] ??
    null;

  if (!selected) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-12 text-center">
          <p className="font-semibold">No candidates awaiting governance</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Candidate evaluation manifests appear here before activation.
          </p>
        </CardContent>
      </Card>
    );
  }

  const canPromote = selected.status === "ready" && selected.decision === "promote";
  const evaluationRows = [
    ["Training", selected.results.training],
    ["Validation", selected.results.validation],
    ["Protected", selected.results.protected],
  ] as const;

  const openConfirmation = () => {
    setConfirmation("");
    setConfirmationKind("promote");
  };

  const confirmPromotion = () => {
    onPromote(selected.id);
    closeConfirmation();
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-2 overflow-x-auto pb-1">
        {candidates.map((candidate) => (
          <button
            key={candidate.id}
            type="button"
            aria-pressed={candidate.id === selected.id}
            onClick={() => setSelectedId(candidate.id)}
            className="min-w-56 rounded-lg border bg-card px-3 py-2 text-left"
          >
            <span className="block text-sm font-semibold">{candidate.title}</span>
            <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
              {candidate.candidate_hash}
            </span>
          </button>
        ))}
      </div>

      <Card className="overflow-hidden border-2 border-foreground">
        <div className="grid sm:grid-cols-[1fr_auto]">
          <CardHeader className="border-b sm:border-b-0 sm:border-r">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Badge>{selected.status}</Badge>
              <span className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
                Candidate evaluation
              </span>
            </div>
            <CardTitle className="text-xl">{selected.title}</CardTitle>
            <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
              {selected.rationale}
            </p>
          </CardHeader>
          <div className="flex min-w-52 flex-col justify-center gap-2 bg-foreground p-5 text-background">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] opacity-60">
              Authority state
            </p>
            <p className="text-lg font-bold">
              {selected.status === "promoted"
                ? "Active candidate"
                : selected.status === "rolled_back"
                  ? "Rolled back"
                : selected.decision === "promote"
                  ? "Eligible, not active"
                  : "Promotion vetoed"}
            </p>
            <p className="font-mono text-[10px] opacity-60">
              {selected.candidate_hash}
            </p>
          </div>
        </div>

        <CardContent className="space-y-5 pt-5">
          <div className="grid gap-2 md:grid-cols-3">
            {evaluationRows.map(([label, result]) => (
              <section key={label} className="rounded-lg border bg-background p-4">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-bold uppercase tracking-[0.15em]">
                    {label}
                  </p>
                  {label === "Protected" && (
                    <ShieldCheck className="h-4 w-4 text-emerald-600" />
                  )}
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <span className="text-lg font-semibold text-muted-foreground">
                    {percent(result.baseline)}
                  </span>
                  <ArrowRight className="h-4 w-4" />
                  <span className="text-2xl font-black">
                    {percent(result.candidate)}
                  </span>
                </div>
                <p
                  className={`mt-2 text-xs font-bold ${
                    result.candidate - result.baseline < 0
                      ? "text-red-700"
                      : "text-emerald-700"
                  }`}
                >
                  {pointDelta(result.baseline, result.candidate)}
                </p>
              </section>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <div className="rounded-lg bg-muted p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Lower bound
              </p>
              <p className="mt-1 font-bold">
                {percent(selected.lower_confidence_bound)}
              </p>
            </div>
            <div className="rounded-lg bg-muted p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Latency
              </p>
              <p className="mt-1 font-bold">{selected.latency_ratio.toFixed(2)}x</p>
            </div>
            <div className="rounded-lg bg-muted p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Cost
              </p>
              <p className="mt-1 font-bold">{selected.cost_ratio.toFixed(2)}x</p>
            </div>
            <div className="rounded-lg bg-muted p-3">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground">
                Scope
              </p>
              <p className="mt-1 font-bold">{selected.mutations.length} mutation</p>
            </div>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-bold uppercase tracking-[0.15em]">
              Proposed mutations
            </p>
            {selected.mutations.map((mutation) => (
              <div
                key={`${mutation.kind}-${mutation.target}-${mutation.summary}`}
                className="grid gap-1 rounded-lg border p-3 text-sm sm:grid-cols-[10rem_10rem_1fr]"
              >
                <code>{mutation.kind}</code>
                <code>{mutation.target}</code>
                <span>{mutation.summary}</span>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-sm">
              <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              <span>
                Parent <code className="text-xs">{selected.parent_hash}</code>{" "}
                remains rollback-safe.
              </span>
            </div>
            {selected.status === "promoted" ? (
              <Button
                variant="destructive"
                onClick={(event) => {
                  event.currentTarget.focus();
                  setConfirmationKind("rollback");
                }}
                disabled={pendingActionIds.has(
                  `candidate:${selected.id}:rollback`
                )}
                aria-label="Rollback candidate"
              >
                <RotateCcw className="h-4 w-4" />
                Rollback candidate
              </Button>
            ) : (
              <Button
                onClick={openConfirmation}
                disabled={
                  !canPromote ||
                  pendingActionIds.has(`candidate:${selected.id}:promote`)
                }
                aria-label="Promote candidate"
              >
                Promote candidate
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      <ConfirmationDialog
        open={confirmationKind === "promote"}
        eyebrow="Active runtime change"
        title="This changes the active agent"
        description="Promotion makes this candidate serve future runs. Verify the evaluation split and type the exact candidate hash."
        identity={
          <code className="text-xs">{selected.candidate_hash}</code>
        }
        outcome="Future runs will use this candidate until it is rolled back."
        confirmLabel="Confirm promotion"
        confirmDisabled={confirmation !== selected.candidate_hash}
        onClose={closeConfirmation}
        onConfirm={confirmPromotion}
      >
        <div>
          <label
            htmlFor="promotion-confirmation"
            className="text-sm font-semibold"
          >
            Type candidate hash to confirm
          </label>
          <Input
            id="promotion-confirmation"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            autoComplete="off"
            className="mt-2 font-mono"
          />
        </div>
      </ConfirmationDialog>
      <ConfirmationDialog
        open={confirmationKind === "rollback"}
        eyebrow="Active runtime rollback"
        title="Rollback this candidate?"
        description="Confirm the exact active candidate and restoration target."
        identity={<code className="text-xs">{selected.candidate_hash}</code>}
        outcome={`This will restore parent ${selected.parent_hash} for future runs.`}
        confirmLabel="Confirm rollback"
        confirmDisabled={pendingActionIds.has(
          `candidate:${selected.id}:rollback`
        )}
        onClose={closeConfirmation}
        onConfirm={() => {
          onRollback(selected.id);
          closeConfirmation();
        }}
      />
    </div>
  );
}
