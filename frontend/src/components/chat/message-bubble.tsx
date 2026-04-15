"use client";

import { cn } from "@/lib/utils";
import { User, Bot, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { ToolCallBlock } from "./tool-call-block";
import type { Message } from "@/lib/types";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isAssistant = message.role === "assistant";
  const isTool = message.role === "tool";

  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex h-8 w-8 shrink-0 items-center justify-center rounded-full",
          isUser && "bg-primary text-primary-foreground",
          isAssistant && "bg-muted",
          isTool && "bg-yellow-500/10 text-yellow-500"
        )}
      >
        {isUser ? (
          <User className="h-4 w-4" />
        ) : isTool ? (
          <Wrench className="h-4 w-4" />
        ) : (
          <Bot className="h-4 w-4" />
        )}
      </div>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-3",
          isUser && "bg-primary text-primary-foreground",
          isAssistant && "bg-muted",
          isTool && "bg-yellow-500/5 border border-yellow-500/20"
        )}
      >
        {isAssistant || isTool ? (
          <div className="prose prose-sm prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
            <ReactMarkdown>{message.content}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm">{message.content}</p>
        )}
        {message.tool_calls && message.tool_calls.length > 0 && (
          <div className="mt-2 space-y-2">
            {message.tool_calls.map((tc) => (
              <ToolCallBlock key={tc.id} toolCall={tc} />
            ))}
          </div>
        )}
        {isStreaming && (
          <span className="ml-1 inline-block h-4 w-1 animate-pulse bg-primary" />
        )}
      </div>
    </div>
  );
}
