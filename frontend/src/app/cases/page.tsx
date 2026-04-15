"use client";

import { useEffect, useState, useCallback } from "react";
import { CaseList } from "@/components/cases/case-list";
import { CreateCaseForm } from "@/components/cases/create-case-form";
import type { EvalCase } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function CasesPage() {
  const [cases, setCases] = useState<EvalCase[]>([]);

  const loadCases = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/cases`);
      if (res.ok) {
        const data = await res.json();
        setCases(data);
      }
    } catch (err) {
      console.error("Load cases error:", err);
    }
  }, []);

  useEffect(() => {
    loadCases();
  }, [loadCases]);

  const handleCreateCase = async (data: {
    name: string;
    input: string;
    expected_output: string;
    tags: string[];
  }) => {
    try {
      const res = await fetch(`${API_BASE}/api/cases`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (res.ok) {
        await loadCases();
      }
    } catch (err) {
      console.error("Create case error:", err);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Test Cases</h2>
          <p className="text-muted-foreground">
            Manage evaluation test cases ({cases.length} total).
          </p>
        </div>
        <CreateCaseForm onSubmit={handleCreateCase} />
      </div>
      <CaseList cases={cases} />
    </div>
  );
}
