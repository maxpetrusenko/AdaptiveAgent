"use client";

import { useState, useCallback, useRef } from "react";
import type { Message, Session } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useChat() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const createSession = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: "New Chat" }),
      });
      if (!res.ok) throw new Error("Failed to create session");
      const session: Session = await res.json();
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(session.id);
      setMessages([]);
      return session;
    } catch (err) {
      console.error("Create session error:", err);
      return null;
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions`);
      if (!res.ok) return;
      const data: Session[] = await res.json();
      setSessions(data);
    } catch (err) {
      console.error("Load sessions error:", err);
    }
  }, []);

  const loadMessages = useCallback(async (sessionId: string) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/chat/sessions/${sessionId}/messages`
      );
      if (!res.ok) return;
      const data: Message[] = await res.json();
      setMessages(data);
    } catch (err) {
      console.error("Load messages error:", err);
    }
  }, []);

  const selectSession = useCallback(
    async (sessionId: string) => {
      setActiveSessionId(sessionId);
      await loadMessages(sessionId);
    },
    [loadMessages]
  );

  const sendMessage = useCallback(
    async (content: string) => {
      let sessionId = activeSessionId;

      // Auto-create session if none active
      if (!sessionId) {
        const session = await createSession();
        if (!session) return;
        sessionId = session.id;
      }

      // Add user message optimistically
      const userMsg: Message = {
        id: `temp-${Date.now()}`,
        session_id: sessionId,
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setIsLoading(true);
      setStreamingContent("");

      try {
        abortRef.current = new AbortController();
        const res = await fetch(`${API_BASE}/api/chat/stream`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: content }),
          signal: abortRef.current.signal,
        });

        if (!res.ok) throw new Error("Stream failed");

        const reader = res.body?.getReader();
        const decoder = new TextDecoder();
        let accumulated = "";

        if (reader) {
          let buffer = "";
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            // Keep the last element as buffer (may be incomplete)
            buffer = lines.pop() ?? "";

            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              const data = line.slice(6).trim();
              if (data === "[DONE]") continue;

              let parsed;
              try {
                parsed = JSON.parse(data);
              } catch {
                continue;
              }

              if (parsed.type === "content") {
                accumulated += parsed.content;
                setStreamingContent(accumulated);
              } else if (parsed.type === "tool_call") {
                accumulated += `\n\n*Using tool: ${parsed.name}*\n`;
                setStreamingContent(accumulated);
              } else if (parsed.type === "tool_result") {
                const output =
                  typeof parsed.output === "string"
                    ? parsed.output.slice(0, 200)
                    : JSON.stringify(parsed.output).slice(0, 200);
                accumulated += `\n*Result: ${output}*\n\n`;
                setStreamingContent(accumulated);
              } else if (parsed.type === "done") {
                setStreamingContent("");
                await loadMessages(sessionId!);
              } else if (parsed.type === "error") {
                accumulated += `\n\n**Error:** ${parsed.error}\n`;
                setStreamingContent(accumulated);
              }
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        console.error("Send error:", err);
        setStreamingContent("");
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            session_id: sessionId!,
            role: "assistant",
            content:
              "Sorry, there was an error processing your message. Make sure the backend is running.",
            created_at: new Date().toISOString(),
          },
        ]);
      } finally {
        setIsLoading(false);
        setStreamingContent("");
        abortRef.current = null;
      }
    },
    [activeSessionId, createSession, loadMessages]
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    sessions,
    activeSessionId,
    messages,
    streamingContent,
    isLoading,
    createSession,
    loadSessions,
    selectSession,
    sendMessage,
    stopStreaming,
  };
}
