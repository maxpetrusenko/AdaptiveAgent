"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { EvalRun } from "@/lib/types";

interface PassRateChartProps {
  runs: EvalRun[];
}

export function PassRateChart({ runs }: PassRateChartProps) {
  const data = runs
    .filter((r) => r.status === "completed" && r.pass_rate != null)
    .map((r) => ({
      date: new Date(r.started_at).toLocaleDateString(),
      passRate: Math.round((r.pass_rate ?? 0) * 100),
    }));

  if (data.length === 0) {
    return (
      <Card className="border-2 border-foreground/10">
        <CardHeader>
          <CardTitle className="text-sm">Pass Rate Over Time</CardTitle>
        </CardHeader>
        <CardContent className="flex h-[200px] items-center justify-center text-sm text-muted-foreground">
          Run evals to see trends here.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-2 border-foreground/10">
      <CardHeader>
        <CardTitle className="text-sm">Pass Rate Over Time</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="#d4cfc5" />
            <XAxis
              dataKey="date"
              stroke="#6b6560"
              fontSize={12}
            />
            <YAxis
              stroke="#6b6560"
              fontSize={12}
              domain={[0, 100]}
              tickFormatter={(v: number) => `${v}%`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#ffffff",
                border: "2px solid #d4cfc5",
                borderRadius: "8px",
                color: "#1a1a1a",
              }}
              formatter={(value) => [`${value}%`, "Pass Rate"]}
            />
            <Line
              type="monotone"
              dataKey="passRate"
              stroke="#c8ff00"
              strokeWidth={3}
              dot={{ fill: "#c8ff00", stroke: "#1a1a1a", strokeWidth: 1, r: 5 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
