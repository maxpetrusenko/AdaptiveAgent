"use client";

import { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  TrendingUp,
  Shield,
  DollarSign,
  FlaskConical,
} from "lucide-react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { DashboardMetrics } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [recentRuns, setRecentRuns] = useState<
    { date: string; passRate: number }[]
  >([]);

  const loadMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/dashboard/metrics`);
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
        if (data.recent_runs) {
          setRecentRuns(
            data.recent_runs.map((r: { date: string; pass_rate: number }) => ({
              date: new Date(r.date).toLocaleDateString(),
              passRate: Math.round((r.pass_rate ?? 0) * 100),
            }))
          );
        }
      }
    } catch (err) {
      console.error("Load metrics error:", err);
    }
  }, []);

  useEffect(() => {
    loadMetrics();
    const interval = setInterval(loadMetrics, 10000);
    return () => clearInterval(interval);
  }, [loadMetrics]);

  const cards = [
    {
      title: "Pass Rate",
      value:
        metrics?.pass_rate != null
          ? `${(metrics.pass_rate * 100).toFixed(0)}%`
          : "\u2014",
      description:
        metrics?.pass_rate != null
          ? "Latest eval run"
          : "No eval runs yet",
      icon: TrendingUp,
      color:
        metrics?.pass_rate != null
          ? metrics.pass_rate >= 0.8
            ? "text-green-500"
            : "text-yellow-500"
          : "",
    },
    {
      title: "Hallucination Rate",
      value:
        metrics?.hallucination_rate != null
          ? `${(metrics.hallucination_rate * 100).toFixed(0)}%`
          : "\u2014",
      description:
        metrics?.hallucination_rate != null
          ? "From latest run"
          : "No data yet",
      icon: Shield,
      color:
        metrics?.hallucination_rate != null
          ? metrics.hallucination_rate <= 0.1
            ? "text-green-500"
            : "text-red-500"
          : "",
    },
    {
      title: "Avg Cost",
      value:
        metrics?.avg_cost != null ? `$${metrics.avg_cost.toFixed(4)}` : "\u2014",
      description: metrics?.avg_cost != null ? "Per eval case" : "No data yet",
      icon: DollarSign,
      color: "",
    },
    {
      title: "Eval Cases",
      value: metrics?.total_eval_cases?.toString() ?? "0",
      description: `${metrics?.total_eval_runs ?? 0} runs, ${metrics?.total_adaptations ?? 0} adaptations`,
      icon: FlaskConical,
      color: "",
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Dashboard</h2>
        <p className="text-muted-foreground">
          Monitor your agent&apos;s performance and improvement over time.
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
              <card.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className={`text-2xl font-bold ${card.color}`}>
                {card.value}
              </div>
              <p className="text-xs text-muted-foreground">{card.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Pass Rate Over Time</CardTitle>
        </CardHeader>
        <CardContent>
          {recentRuns.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={recentRuns}>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="hsl(var(--border))"
                />
                <XAxis
                  dataKey="date"
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={12}
                />
                <YAxis
                  stroke="hsl(var(--muted-foreground))"
                  fontSize={12}
                  domain={[0, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="passRate"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2}
                  dot={{ fill: "hsl(var(--primary))", r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-[300px] items-center justify-center text-muted-foreground">
              Run your first eval to see metrics here.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
