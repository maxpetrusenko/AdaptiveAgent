"use client";

import { useState, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Play, Loader2 } from "lucide-react";
import { EvalRunList } from "@/components/evals/eval-run-list";
import { EvalResultsTable } from "@/components/evals/eval-results-table";
import { PassRateChart } from "@/components/evals/pass-rate-chart";
import type { EvalRun, EvalResult } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function EvalsPage() {
  const [runs, setRuns] = useState<EvalRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [results, setResults] = useState<EvalResult[]>([]);
  const [isRunning, setIsRunning] = useState(false);

  const loadRuns = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/evals/runs`);
      if (res.ok) {
        const data = await res.json();
        setRuns(data);
      }
    } catch (err) {
      console.error("Load runs error:", err);
    }
  }, []);

  const loadResults = useCallback(async (runId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/evals/runs/${runId}/results`);
      if (res.ok) {
        const data = await res.json();
        setResults(data);
      }
    } catch (err) {
      console.error("Load results error:", err);
    }
  }, []);

  const initialized = useRef<boolean | null>(null);
  if (initialized.current === null) {
    initialized.current = true;
    loadRuns();
  }

  const handleSelectRun = (id: string) => {
    setSelectedRunId(id);
    loadResults(id);
  };

  const handleRunEval = async () => {
    setIsRunning(true);
    try {
      const res = await fetch(`${API_BASE}/api/evals/run`, { method: "POST" });
      if (res.ok) {
        const data = await res.json();
        const pollInterval = setInterval(async () => {
          try {
            const statusRes = await fetch(`${API_BASE}/api/evals/runs/${data.id}`);
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              if (statusData.status === "completed" || statusData.status === "failed") {
                clearInterval(pollInterval);
                setIsRunning(false);
                await loadRuns();
                handleSelectRun(data.id);
              }
            }
          } catch {
            clearInterval(pollInterval);
            setIsRunning(false);
          }
        }, 2000);
      } else {
        setIsRunning(false);
      }
    } catch (err) {
      console.error("Run eval error:", err);
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Evaluations</h2>
          <p className="text-muted-foreground">
            Run and review agent evaluation results.
          </p>
        </div>
        <Button onClick={handleRunEval} disabled={isRunning}>
          {isRunning ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Play className="mr-2 h-4 w-4" />
              Run Eval
            </>
          )}
        </Button>
      </div>

      <PassRateChart runs={runs} />

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 text-lg font-semibold">Eval Runs</h3>
          <EvalRunList
            runs={runs}
            selectedRunId={selectedRunId ?? undefined}
            onSelect={handleSelectRun}
          />
        </div>
        <div>
          <h3 className="mb-3 text-lg font-semibold">Results</h3>
          <EvalResultsTable results={results} />
        </div>
      </div>
    </div>
  );
}
