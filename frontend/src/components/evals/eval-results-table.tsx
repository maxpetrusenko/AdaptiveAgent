"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { EvalResult } from "@/lib/types";

interface EvalResultsTableProps {
  results: EvalResult[];
}

export function EvalResultsTable({ results }: EvalResultsTableProps) {
  if (results.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
        Select an eval run to see results.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {results.map((result) => (
        <Card key={result.id} className="border-2 border-foreground/10">
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <Badge
                    className={cn(
                      "border-0",
                      result.status === "pass"
                        ? "bg-green-100 text-green-700"
                        : result.status === "fail"
                        ? "bg-red-100 text-red-700"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {result.status}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {result.latency_ms}ms
                  </span>
                  {result.score != null && (
                    <span className="text-xs text-muted-foreground">
                      Score: {result.score.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="rounded bg-muted/50 p-2 text-sm">
                  <p className="font-medium">Output:</p>
                  <p className="mt-1 text-muted-foreground whitespace-pre-wrap">
                    {result.actual_output.slice(0, 500)}
                    {result.actual_output.length > 500 && "..."}
                  </p>
                </div>
                {result.error && (
                  <div className="rounded bg-destructive/10 p-2 text-sm text-destructive">
                    {result.error}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
