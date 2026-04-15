"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ArrowRight, Check, X } from "lucide-react";
import type { AdaptationRun } from "@/lib/types";

interface AdaptationListProps {
  runs: AdaptationRun[];
  selectedId?: string;
  onSelect: (id: string) => void;
}

export function AdaptationList({
  runs,
  selectedId,
  onSelect,
}: AdaptationListProps) {
  if (runs.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">
          No adaptation runs yet. Click &quot;Improve&quot; to start the
          self-improving loop.
        </p>
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
            run.id === selectedId && "ring-primary bg-accent/30"
          )}
          onClick={() => onSelect(run.id)}
        >
          <CardContent className="!py-0 p-4">
            <div className="flex items-center justify-between">
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      run.status === "completed"
                        ? run.accepted
                          ? "default"
                          : "secondary"
                        : run.status === "running"
                          ? "secondary"
                          : "destructive"
                    }
                  >
                    {run.status === "completed"
                      ? run.accepted
                        ? "Accepted"
                        : "Rejected"
                      : run.status}
                  </Badge>
                  {run.accepted ? (
                    <Check className="h-4 w-4 text-green-500" />
                  ) : run.status === "completed" ? (
                    <X className="h-4 w-4 text-red-500" />
                  ) : null}
                </div>
                <span className="text-xs text-muted-foreground">
                  {new Date(run.started_at).toLocaleString()}
                </span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span
                  className={cn(
                    "font-bold",
                    run.before_pass_rate >= 0.8
                      ? "text-green-500"
                      : "text-yellow-500"
                  )}
                >
                  {(run.before_pass_rate * 100).toFixed(0)}%
                </span>
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <span
                  className={cn(
                    "font-bold",
                    run.after_pass_rate != null
                      ? run.after_pass_rate >= 0.8
                        ? "text-green-500"
                        : "text-yellow-500"
                      : "text-muted-foreground"
                  )}
                >
                  {run.after_pass_rate != null
                    ? `${(run.after_pass_rate * 100).toFixed(0)}%`
                    : "\u2014"}
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
