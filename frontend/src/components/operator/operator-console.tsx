"use client";

import { useState } from "react";

import { PromotionGate } from "@/components/operator/promotion-gate";
import { TaskLedger } from "@/components/operator/task-ledger";
import type {
  OperatorTask,
  PromotionCandidate,
  TaskAction,
} from "@/lib/operator-types";

interface OperatorConsoleProps {
  tasks: OperatorTask[];
  candidates: PromotionCandidate[];
  onTaskAction: (taskId: string, action: TaskAction) => void;
  onPromote: (candidateId: string) => void;
  onRollback: (candidateId: string) => void;
  pendingActionIds?: ReadonlySet<string>;
}

export function OperatorConsole({
  tasks,
  candidates,
  onTaskAction,
  onPromote,
  onRollback,
  pendingActionIds,
}: OperatorConsoleProps) {
  const [selectedTaskId, setSelectedTaskId] = useState(tasks[0]?.id ?? null);

  return (
    <div className="space-y-10">
      <section aria-labelledby="task-ledger-heading" className="space-y-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">
            Long-horizon execution
          </p>
          <h2
            id="task-ledger-heading"
            className="mt-1 text-3xl font-black tracking-tight"
          >
            Mission ledger
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            One durable record for the plan, pressure signals, lifecycle, and
            evidence required to call the work complete.
          </p>
        </div>
        <TaskLedger
          tasks={tasks}
          selectedTaskId={selectedTaskId}
          onSelect={setSelectedTaskId}
          onAction={onTaskAction}
          pendingActionIds={pendingActionIds}
        />
      </section>

      <section aria-labelledby="promotion-heading" className="space-y-4">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.22em] text-muted-foreground">
            Self-improvement authority
          </p>
          <h2
            id="promotion-heading"
            className="mt-1 text-3xl font-black tracking-tight"
          >
            Promotion gate
          </h2>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Training informs the proposal. Validation decides. Protected cases
            can veto. Activation always remains an explicit operator action.
          </p>
        </div>
        <PromotionGate
          candidates={candidates}
          onPromote={onPromote}
          onRollback={onRollback}
          pendingActionIds={pendingActionIds}
        />
      </section>
    </div>
  );
}
