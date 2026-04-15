"use client";

import { useEffect } from "react";
import { MessageList } from "@/components/chat/message-list";
import { ChatInput } from "@/components/chat/chat-input";
import { SessionList } from "@/components/chat/session-list";
import { useChat } from "@/hooks/use-chat";

export default function ChatPage() {
  const {
    sessions,
    activeSessionId,
    messages,
    streamingContent,
    isLoading,
    createSession,
    loadSessions,
    selectSession,
    sendMessage,
  } = useChat();

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  return (
    <div className="-m-6 flex h-[calc(100vh)] overflow-hidden">
      <SessionList
        sessions={sessions}
        activeSessionId={activeSessionId ?? undefined}
        onSelect={selectSession}
        onCreate={createSession}
      />
      <div className="flex flex-1 flex-col bg-background">
        <div className="border-b border-border px-4 py-3">
          <h2 className="text-lg font-semibold">
            {activeSessionId ? "Chat" : "Start a new conversation"}
          </h2>
        </div>
        <MessageList messages={messages} streamingContent={streamingContent} />
        <ChatInput onSend={sendMessage} disabled={isLoading} />
      </div>
    </div>
  );
}
