"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { EvalRun } from "@/lib/types";

interface EvalRunListProps {
  runs: EvalRun[];
  selectedRunId?: string;
  onSelect: (id: string) => void;
}

export function EvalRunList({ runs, selectedRunId, onSelect }: EvalRunListProps) {
  if (runs.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No eval runs yet. Click &quot;Run Eval&quot; to start.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {runs.map((run) => (
        <Card
          key={run.id}
          className={cn(
            "cursor-pointer transition-colors hover:bg-accent/50",
            run.id === selectedRunId && "border-primary bg-accent/30"
          )}
          onClick={() => onSelect(run.id)}
        >
          <CardContent className="flex items-center justify-between p-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    run.status === "completed"
                      ? "default"
                      : run.status === "running"
                      ? "secondary"
                      : "destructive"
                  }
                >
                  {run.status}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {new Date(run.started_at).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <span>
                  <strong>{run.passed}</strong> passed
                </span>
                <span>
                  <strong>{run.failed}</strong> failed
                </span>
                <span>
                  <strong>{run.total}</strong> total
                </span>
              </div>
            </div>
            {run.pass_rate != null && (
              <div className="text-right">
                <div
                  className={cn(
                    "text-2xl font-bold",
                    run.pass_rate >= 0.8
                      ? "text-green-500"
                      : run.pass_rate >= 0.5
                      ? "text-yellow-500"
                      : "text-red-500"
                  )}
                >
                  {(run.pass_rate * 100).toFixed(0)}%
                </div>
                <span className="text-xs text-muted-foreground">pass rate</span>
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
