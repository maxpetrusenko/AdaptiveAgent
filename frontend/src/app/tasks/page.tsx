"use client";

import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { OperatorConsole } from "@/components/operator/operator-console";
import { Button } from "@/components/ui/button";
import { operatorApi } from "@/lib/operator-api";
import type {
  OperatorTask,
  PromotionCandidate,
  TaskAction,
} from "@/lib/operator-types";

const operatorSessionError =
  "Operator session required. Sign in through the backend operator session; never expose OPERATOR_API_TOKEN through NEXT_PUBLIC variables.";

const requiresOperatorSession = (error: unknown) =>
  typeof error === "object" &&
  error !== null &&
  "status" in error &&
  (error.status === 401 || error.status === 403);

export default function TasksPage() {
  const [tasks, setTasks] = useState<OperatorTask[]>([]);
  const [candidates, setCandidates] = useState<PromotionCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pendingActionIds, setPendingActionIds] = useState<Set<string>>(
    new Set()
  );
  const pendingActionIdsRef = useRef(new Set<string>());

  const beginAction = (key: string) => {
    if (pendingActionIdsRef.current.has(key)) {
      return false;
    }
    pendingActionIdsRef.current.add(key);
    setPendingActionIds(new Set(pendingActionIdsRef.current));
    return true;
  };

  const finishAction = (key: string) => {
    pendingActionIdsRef.current.delete(key);
    setPendingActionIds(new Set(pendingActionIdsRef.current));
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [tasksResult, candidatesResult] = await Promise.allSettled([
      operatorApi.listTasks(),
      operatorApi.listCandidates(),
    ]);

    if (tasksResult.status === "fulfilled") {
      setTasks(tasksResult.value);
    }
    if (candidatesResult.status === "fulfilled") {
      setCandidates(candidatesResult.value);
    }
    if (
      tasksResult.status === "rejected" ||
      candidatesResult.status === "rejected"
    ) {
      setError(
        "Some operator evidence is unavailable. Retry after the API is reachable."
      );
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      const [tasksResult, candidatesResult] = await Promise.allSettled([
        operatorApi.listTasks(),
        operatorApi.listCandidates(),
      ]);
      if (cancelled) {
        return;
      }
      if (tasksResult.status === "fulfilled") {
        setTasks(tasksResult.value);
      }
      if (candidatesResult.status === "fulfilled") {
        setCandidates(candidatesResult.value);
      }
      if (
        tasksResult.status === "rejected" ||
        candidatesResult.status === "rejected"
      ) {
        setError(
          "Some operator evidence is unavailable. Retry after the API is reachable."
        );
      }
      setLoading(false);
    };

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const transitionTask = async (taskId: string, action: TaskAction) => {
    const key = `task:${taskId}`;
    if (!beginAction(key)) {
      return;
    }
    try {
      const updated = await operatorApi.transitionTask(taskId, action);
      setTasks((current) =>
        current.map((task) => (task.id === updated.id ? updated : task))
      );
    } catch (caught) {
      setError(
        requiresOperatorSession(caught)
          ? operatorSessionError
          : `Could not ${action} the selected task.`
      );
    } finally {
      finishAction(key);
    }
  };

  const promoteCandidate = async (candidateId: string) => {
    const key = `candidate:${candidateId}:promote`;
    if (!beginAction(key)) {
      return;
    }
    try {
      const updated = await operatorApi.promoteCandidate(candidateId);
      setCandidates((current) =>
        current.map((candidate) =>
          candidate.id === updated.id ? updated : candidate
        )
      );
    } catch (caught) {
      setError(
        requiresOperatorSession(caught)
          ? operatorSessionError
          : "Promotion failed. The previous active version is unchanged."
      );
    } finally {
      finishAction(key);
    }
  };

  const rollbackCandidate = async (candidateId: string) => {
    const key = `candidate:${candidateId}:rollback`;
    if (!beginAction(key)) {
      return;
    }
    try {
      const updated = await operatorApi.rollbackCandidate(candidateId);
      setCandidates((current) =>
        current.map((candidate) =>
          candidate.id === updated.id ? updated : candidate
        )
      );
    } catch (caught) {
      setError(
        requiresOperatorSession(caught)
          ? operatorSessionError
          : "Rollback failed. Check the active candidate before retrying."
      );
    } finally {
      finishAction(key);
    }
  };

  if (loading) {
    return (
      <div className="grid min-h-[60vh] place-items-center" role="status">
        <div className="text-center">
          <Loader2 className="mx-auto h-6 w-6 animate-spin" />
          <p className="mt-3 text-sm font-semibold">Loading operator ledger</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1500px]">
      {error && (
        <div
          role="alert"
          className="mb-5 flex flex-col gap-3 rounded-lg border border-orange-500/50 bg-orange-500/10 p-3 text-sm sm:flex-row sm:items-center sm:justify-between"
        >
          <span className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </span>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      )}
      <OperatorConsole
        tasks={tasks}
        candidates={candidates}
        onTaskAction={(taskId, action) => void transitionTask(taskId, action)}
        onPromote={(candidateId) => void promoteCandidate(candidateId)}
        onRollback={(candidateId) => void rollbackCandidate(candidateId)}
        pendingActionIds={pendingActionIds}
      />
    </div>
  );
}
