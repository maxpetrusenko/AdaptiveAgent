"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface PromptDiffProps {
  beforePrompt: string;
  afterPrompt: string;
  changeReason?: string;
}

export function PromptDiff({
  beforePrompt,
  afterPrompt,
  changeReason,
}: PromptDiffProps) {
  const beforeLines = beforePrompt.split("\n");
  const afterLines = afterPrompt.split("\n");

  const maxLines = Math.max(beforeLines.length, afterLines.length);
  const diffLines: { type: "same" | "removed" | "added"; content: string }[] =
    [];

  for (let i = 0; i < maxLines; i++) {
    const before = beforeLines[i] ?? "";
    const after = afterLines[i] ?? "";
    if (before === after) {
      diffLines.push({ type: "same", content: before });
    } else {
      if (before) diffLines.push({ type: "removed", content: before });
      if (after) diffLines.push({ type: "added", content: after });
    }
  }

  return (
    <Card className="border-2 border-foreground/10">
      <CardHeader>
        <CardTitle className="text-sm">Prompt Changes</CardTitle>
        {changeReason && (
          <p className="text-xs text-muted-foreground">{changeReason}</p>
        )}
      </CardHeader>
      <CardContent>
        <Tabs defaultValue={0}>
          <TabsList>
            <TabsTrigger value={0}>Diff</TabsTrigger>
            <TabsTrigger value={1}>Before</TabsTrigger>
            <TabsTrigger value={2}>After</TabsTrigger>
          </TabsList>
          <TabsContent value={0} className="mt-2">
            <pre className="max-h-[400px] overflow-auto rounded bg-muted/50 p-3 text-xs font-mono">
              {diffLines.map((line, i) => (
                <div
                  key={i}
                  className={
                    line.type === "removed"
                      ? "bg-red-100 text-red-700"
                      : line.type === "added"
                        ? "bg-[#c8ff00]/20 text-green-700"
                        : "text-muted-foreground"
                  }
                >
                  {line.type === "removed" && "- "}
                  {line.type === "added" && "+ "}
                  {line.type === "same" && "  "}
                  {line.content}
                </div>
              ))}
            </pre>
          </TabsContent>
          <TabsContent value={1} className="mt-2">
            <pre className="max-h-[400px] overflow-auto rounded bg-muted/50 p-3 text-xs font-mono text-muted-foreground whitespace-pre-wrap">
              {beforePrompt}
            </pre>
          </TabsContent>
          <TabsContent value={2} className="mt-2">
            <pre className="max-h-[400px] overflow-auto rounded bg-muted/50 p-3 text-xs font-mono text-muted-foreground whitespace-pre-wrap">
              {afterPrompt}
            </pre>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
