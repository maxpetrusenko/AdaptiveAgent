"use client";

import {
  AlertTriangle,
  Check,
  Circle,
  ExternalLink,
  Pause,
  Play,
  Square,
} from "lucide-react";
import { useCallback, useState } from "react";

import { ConfirmationDialog } from "@/components/operator/confirmation-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { safeArtifactHref } from "@/lib/safe-artifact";
import type {
  OperatorTask,
  TaskAction,
  TaskEvidence,
  TaskStatus,
} from "@/lib/operator-types";

const statusTone: Record<TaskStatus, string> = {
  active: "border-lime-500/40 bg-lime-500/10 text-foreground",
  paused: "border-amber-500/40 bg-amber-500/10 text-foreground",
  completed: "border-emerald-500/40 bg-emerald-500/10 text-foreground",
  cancelled: "border-red-500/40 bg-red-500/10 text-foreground",
  escalated: "border-orange-500/40 bg-orange-500/10 text-foreground",
  replan_required: "border-orange-500/40 bg-orange-500/10 text-foreground",
};

interface TaskLedgerProps {
  tasks: OperatorTask[];
  selectedTaskId: string | null;
  onSelect: (taskId: string) => void;
  onAction: (taskId: string, action: TaskAction) => void;
  pendingActionIds?: ReadonlySet<string>;
}

const statusLabel = (status: TaskStatus) =>
  status === "replan_required" ? "Replan required" : status;

const isVerifiedAnchored = (proof: TaskEvidence) =>
  proof.status === "verified" &&
  Boolean(proof.digest || safeArtifactHref(proof.artifact_ref));

function Metric({
  label,
  value,
  pressure,
}: {
  label: string;
  value: string;
  pressure?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border bg-card px-3 py-2",
        pressure && "border-orange-500/50 bg-orange-500/5"
      )}
    >
      <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export function TaskLedger({
  tasks,
  selectedTaskId,
  onSelect,
  onAction,
  pendingActionIds = new Set(),
}: TaskLedgerProps) {
  const [cancelTaskId, setCancelTaskId] = useState<string | null>(null);
  const closeCancelDialog = useCallback(() => setCancelTaskId(null), []);
  const selected =
    tasks.find((task) => task.id === selectedTaskId) ?? tasks[0] ?? null;

  if (!selected) {
    return (
      <Card className="border-dashed">
        <CardContent className="py-12 text-center">
          <p className="font-semibold">No durable tasks yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            POST a task to the ledger to make its plan and proof visible here.
          </p>
        </CardContent>
      </Card>
    );
  }

  const canOperate =
    selected.status === "active" ||
    selected.status === "paused" ||
    selected.status === "replan_required";
  const stallPressure =
    selected.stall_count >= Math.max(selected.stall_threshold - 1, 1);
  const budgetPressure =
    selected.actions_used / selected.action_budget >= 0.75;
  const lifecyclePending = pendingActionIds.has(`task:${selected.id}`);

  return (
    <div className="grid gap-4 xl:grid-cols-[17rem_minmax(0,1fr)]">
      <Card className="h-fit border-2 border-foreground/10">
        <CardHeader className="pb-2">
          <CardTitle className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
            Live tasks
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {tasks.map((task) => (
            <button
              key={task.id}
              type="button"
              onClick={() => onSelect(task.id)}
              aria-pressed={task.id === selected.id}
              className={cn(
                "w-full rounded-lg border px-3 py-3 text-left transition",
                task.id === selected.id
                  ? "border-foreground bg-foreground text-background"
                  : "border-border bg-background hover:border-foreground/40"
              )}
            >
              <span className="block line-clamp-2 text-sm font-semibold">
                {task.goal}
              </span>
              <span className="mt-2 flex items-center justify-between text-[11px] uppercase tracking-wide opacity-65">
                <span>{task.status}</span>
                <span>v{task.plan_version}</span>
              </span>
            </button>
          ))}
        </CardContent>
      </Card>

      <div className="min-w-0 space-y-4">
        <Card className="overflow-hidden border-2 border-foreground/10">
          <div className="h-1.5 bg-[var(--primary)]" />
          <CardHeader className="gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge className={cn("border", statusTone[selected.status])}>
                  {statusLabel(selected.status)}
                </Badge>
                <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Plan v{selected.plan_version}
                </span>
              </div>
              <h3 className="text-xl font-semibold leading-tight sm:text-2xl">
                {selected.goal}
              </h3>
              <p className="mt-2 text-xs text-muted-foreground">
                Updated {new Date(selected.updated_at).toLocaleString()}
              </p>
            </div>
            {canOperate && (
              <div className="flex shrink-0 flex-wrap gap-2">
                {selected.status === "active" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onAction(selected.id, "pause")}
                    disabled={lifecyclePending}
                    aria-label="Pause task"
                  >
                    <Pause className="h-4 w-4" />
                    Pause
                  </Button>
                ) : selected.status === "paused" ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onAction(selected.id, "resume")}
                    disabled={lifecyclePending}
                    aria-label="Resume task"
                  >
                    <Play className="h-4 w-4" />
                    Resume
                  </Button>
                ) : null}
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => setCancelTaskId(selected.id)}
                  disabled={lifecyclePending}
                  aria-label="Cancel task"
                >
                  <Square className="h-3.5 w-3.5" />
                  Cancel
                </Button>
              </div>
            )}
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Metric label="Plan" value={`v${selected.plan_version}`} />
              <Metric
                label="Stall"
                value={`${selected.stall_count} / ${selected.stall_threshold} stalls`}
                pressure={stallPressure}
              />
              <Metric
                label="Budget"
                value={`${selected.actions_used} / ${selected.action_budget} actions`}
                pressure={budgetPressure}
              />
              <Metric
                label="Proof"
                value={`${selected.acceptance_criteria.filter((item) => item.evidence.some(isVerifiedAnchored)).length} / ${selected.acceptance_criteria.length} criteria`}
              />
            </div>
            {(selected.replan_reason || selected.escalation_reason) && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-orange-500/40 bg-orange-500/5 p-3 text-sm">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-orange-600" />
                <span>
                  {selected.escalation_reason
                    ? `Escalated: ${selected.escalation_reason}`
                    : selected.status === "replan_required"
                      ? `Replan required before execution can continue: ${selected.replan_reason}`
                      : `Replanned: ${selected.replan_reason}`}
                </span>
              </div>
            )}
            <div className="mt-3 rounded-lg border bg-muted/40 p-3 text-xs">
              <p className="font-bold">Checkpoint #{selected.checkpoint.sequence}</p>
              <p className="mt-1 text-muted-foreground">
                {selected.checkpoint.operation}
                {selected.checkpoint.idempotency_key
                  ? ` · ${selected.checkpoint.idempotency_key}`
                  : ""}
              </p>
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="border-2 border-foreground/10">
            <CardHeader>
              <CardTitle className="text-sm uppercase tracking-[0.16em]">
                Execution timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="space-y-0">
                {selected.steps.map((step, index) => (
                  <li key={step.id} className="relative flex gap-3 pb-5 last:pb-0">
                    {index < selected.steps.length - 1 && (
                      <span className="absolute left-[9px] top-5 h-full w-px bg-border" />
                    )}
                    <span
                      className={cn(
                        "relative z-10 mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border bg-background",
                        step.status === "active" &&
                          "border-foreground bg-[var(--primary)]",
                        step.status === "completed" &&
                          "border-emerald-600 bg-emerald-600 text-white"
                      )}
                    >
                      {step.status === "completed" ? (
                        <Check className="h-3 w-3" />
                      ) : (
                        <Circle className="h-2.5 w-2.5" />
                      )}
                    </span>
                    <div>
                      <p className="text-sm font-semibold">{step.title}</p>
                      <p className="mt-0.5 text-[11px] uppercase tracking-wider text-muted-foreground">
                        {step.status}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>

          <Card className="border-2 border-foreground/10">
            <CardHeader>
              <CardTitle className="text-sm uppercase tracking-[0.16em]">
                Acceptance proof
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {selected.acceptance_criteria.map((criterion) => (
                (() => {
                  const proven = criterion.evidence.some(isVerifiedAnchored);
                  return (
                <section
                  key={criterion.id}
                  className="rounded-lg border bg-background p-3"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold">
                        {criterion.description}
                      </p>
                      <p className="mt-1 font-mono text-[10px] text-muted-foreground">
                        {criterion.id}
                      </p>
                    </div>
                    <Badge variant="secondary">
                      {proven
                        ? "Proven"
                        : criterion.evidence.length
                          ? "Unverified"
                          : "Missing"}
                    </Badge>
                  </div>
                  {criterion.evidence.map((proof) => {
                    const href = safeArtifactHref(proof.artifact_ref);
                    const verified = isVerifiedAnchored(proof);
                    return (
                    <div
                      key={`${proof.recorded_at}-${proof.summary}`}
                      className={cn(
                        "mt-3 border-l-2 pl-3",
                        verified
                          ? "border-emerald-500"
                          : "border-amber-500"
                      )}
                    >
                      <p className="text-sm">{proof.summary}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {verified ? "Verified" : "Submitted"} by {proof.verifier}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        Source: {proof.source}
                      </p>
                      {proof.digest && (
                        <code className="mt-1 block break-all text-[11px]">
                          {proof.digest}
                        </code>
                      )}
                      {href && (
                        <a
                          href={href}
                          className="mt-1 inline-flex items-center gap-1 text-xs font-semibold underline underline-offset-4"
                        >
                          {href.startsWith("trace:")
                            ? `Open trace ${href}`
                            : `Open proof from ${new URL(href).hostname}`}
                          <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                      {proof.artifact_ref && !href && (
                        <code className="mt-1 block break-all text-[11px]">
                          {proof.artifact_ref}
                        </code>
                      )}
                    </div>
                    );
                  })}
                </section>
                  );
                })()
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
      <ConfirmationDialog
        open={cancelTaskId === selected.id}
        eyebrow="Permanent task transition"
        title="Cancel this task?"
        description="Confirm the exact durable task before changing its lifecycle."
        identity={selected.goal}
        outcome="This task cannot be resumed after cancellation."
        confirmLabel="Confirm task cancellation"
        onClose={closeCancelDialog}
        onConfirm={() => {
          onAction(selected.id, "cancel");
          closeCancelDialog();
        }}
      />
    </div>
  );
}
