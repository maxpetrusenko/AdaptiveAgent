"use client";

import { useState, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Sparkles, Loader2 } from "lucide-react";
import { AdaptationList } from "@/components/adapt/adaptation-list";
import { PromptDiff } from "@/components/adapt/prompt-diff";
import type { AdaptationRun, PromptVersion } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AdaptationDetail {
  run: AdaptationRun;
  before_prompt: PromptVersion;
  after_prompt?: PromptVersion;
}

export default function AdaptPage() {
  const [runs, setRuns] = useState<AdaptationRun[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<AdaptationDetail | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const loadRuns = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/adapt/runs`);
      if (res.ok) {
        const data = await res.json();
        setRuns(data);
      }
    } catch (err) {
      console.error("Load adapt runs error:", err);
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/adapt/runs/${id}`);
      if (res.ok) {
        const data = await res.json();
        setDetail(data);
      }
    } catch (err) {
      console.error("Load detail error:", err);
    }
  }, []);

  const initialized = useRef<boolean | null>(null);
  if (initialized.current === null) {
    initialized.current = true;
    loadRuns();
  }

  const handleSelect = useCallback(
    (id: string) => {
      setSelectedId(id);
      loadDetail(id);
    },
    [loadDetail]
  );

  const handleImprove = async () => {
    setIsRunning(true);
    try {
      const res = await fetch(`${API_BASE}/api/adapt/improve`, {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        const pollInterval = setInterval(async () => {
          try {
            const statusRes = await fetch(
              `${API_BASE}/api/adapt/runs/${data.id}`
            );
            if (statusRes.ok) {
              const statusData = await statusRes.json();
              if (
                statusData.run.status === "completed" ||
                statusData.run.status === "failed" ||
                statusData.run.status === "rejected"
              ) {
                clearInterval(pollInterval);
                setIsRunning(false);
                await loadRuns();
                handleSelect(data.id);
              }
            }
          } catch {
            clearInterval(pollInterval);
            setIsRunning(false);
          }
        }, 3000);
      } else {
        setIsRunning(false);
      }
    } catch (err) {
      console.error("Improve error:", err);
      setIsRunning(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Adaptation</h2>
          <p className="text-muted-foreground">
            Self-improving loop: eval &rarr; detect failures &rarr; update
            prompt &rarr; re-eval.
          </p>
        </div>
        <Button onClick={handleImprove} disabled={isRunning}>
          {isRunning ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Improving...
            </>
          ) : (
            <>
              <Sparkles className="mr-2 h-4 w-4" />
              Improve
            </>
          )}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 text-lg font-semibold">Adaptation History</h3>
          <AdaptationList
            runs={runs}
            selectedId={selectedId ?? undefined}
            onSelect={handleSelect}
          />
        </div>
        <div>
          <h3 className="mb-3 text-lg font-semibold">Details</h3>
          {detail ? (
            <div className="space-y-4">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Pass Rate Change</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex items-center gap-4 text-2xl font-bold">
                    <span>
                      {(detail.run.before_pass_rate * 100).toFixed(0)}%
                    </span>
                    <span className="text-muted-foreground">&rarr;</span>
                    <span>
                      {detail.run.after_pass_rate != null
                        ? `${(detail.run.after_pass_rate * 100).toFixed(0)}%`
                        : "\u2014"}
                    </span>
                    {detail.run.accepted && (
                      <span className="text-sm text-green-500">Accepted</span>
                    )}
                    {detail.run.status === "completed" &&
                      !detail.run.accepted && (
                        <span className="text-sm text-red-500">Rejected</span>
                      )}
                  </div>
                </CardContent>
              </Card>
              {detail.after_prompt && (
                <PromptDiff
                  beforePrompt={detail.before_prompt.content}
                  afterPrompt={detail.after_prompt.content}
                  changeReason={detail.after_prompt.change_reason ?? undefined}
                />
              )}
            </div>
          ) : (
            <div className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
              Select an adaptation run to see details.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
