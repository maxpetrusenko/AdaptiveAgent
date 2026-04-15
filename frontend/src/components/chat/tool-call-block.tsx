"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Wrench } from "lucide-react";
import type { ToolCall } from "@/lib/types";

interface ToolCallBlockProps {
  toolCall: ToolCall;
}

export function ToolCallBlock({ toolCall }: ToolCallBlockProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="rounded-md border border-border bg-background/50">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-2 px-3 py-2 text-xs hover:bg-accent/50"
      >
        {isOpen ? (
          <ChevronDown className="h-3 w-3" />
        ) : (
          <ChevronRight className="h-3 w-3" />
        )}
        <Wrench className="h-3 w-3 text-muted-foreground" />
        <span className="font-mono font-medium">{toolCall.name}</span>
        {toolCall.is_error && (
          <span className="ml-auto rounded bg-destructive/10 px-1.5 py-0.5 text-[10px] font-medium text-destructive">
            Error
          </span>
        )}
      </button>
      {isOpen && (
        <div className="border-t border-border px-3 py-2">
          <div className="space-y-2 text-xs">
            <div>
              <span className="text-muted-foreground">Input:</span>
              <pre className="mt-1 overflow-auto rounded bg-background p-2 font-mono">
                {JSON.stringify(toolCall.input, null, 2)}
              </pre>
            </div>
            {toolCall.output && (
              <div>
                <span className="text-muted-foreground">Output:</span>
                <pre className="mt-1 overflow-auto rounded bg-background p-2 font-mono">
                  {toolCall.output}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
