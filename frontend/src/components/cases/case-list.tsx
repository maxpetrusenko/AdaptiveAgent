"use client";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { EvalCase } from "@/lib/types";

interface CaseListProps {
  cases: EvalCase[];
}

export function CaseList({ cases }: CaseListProps) {
  if (cases.length === 0) {
    return (
      <div className="flex h-[200px] items-center justify-center rounded-lg border border-dashed border-border">
        <p className="text-sm text-muted-foreground">No test cases yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {cases.map((c) => (
        <Card key={c.id} className="border-2 border-foreground/10">
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-sm">{c.name}</span>
                  <Badge variant={c.source === "manual" ? "secondary" : "outline"}>
                    {c.source}
                  </Badge>
                </div>
                <div className="rounded bg-muted/50 p-2 text-sm">
                  <p className="text-muted-foreground">
                    <strong>Input:</strong> {c.input}
                  </p>
                  <p className="mt-1 text-muted-foreground">
                    <strong>Expected:</strong> {c.expected_output}
                  </p>
                </div>
                {c.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {c.tags.map((tag) => (
                      <Badge key={tag} variant="outline" className="text-[10px] border-foreground/15 px-2 py-0">
                        {tag}
                      </Badge>
                    ))}
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
