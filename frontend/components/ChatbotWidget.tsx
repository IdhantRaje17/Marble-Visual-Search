"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Bot, LoaderCircle, RotateCcw, Send, Sparkles, X } from "lucide-react";
import api from "@/lib/api";

type ChatMessage = {
  id: number | string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
};

type ConversationResponse = {
  conversation_id: number | null;
  messages: ChatMessage[];
};

type MessageResponse = {
  conversation_id: number;
  user_message: ChatMessage;
  assistant_message: ChatMessage;
};

export default function ChatbotWidget() {
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    api.get<ConversationResponse>("/api/chat/conversation")
      .then(({ data }) => {
        if (!active) return;
        setConversationId(data.conversation_id);
        setMessages(data.messages);
      })
      .catch(() => {
        if (active) setError("Chat history could not be loaded. Please try again.");
      })
      .finally(() => {
        if (active) setLoadingHistory(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, open]);

  const sendMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const message = draft.trim();
    if (!message || sending) return;

    setDraft("");
    setError("");
    setSending(true);
    setMessages((current) => [
      ...current,
      { id: `pending-${Date.now()}`, role: "user", content: message },
    ]);

    try {
      const { data } = await api.post<MessageResponse>("/api/chat/messages", {
        message,
        conversation_id: conversationId,
      });
      setConversationId(data.conversation_id);
      setMessages((current) => [
        ...current,
        { ...data.assistant_message, id: `reply-${data.assistant_message.id}` },
      ]);
    } catch {
      setError("Your message could not be sent. Please try again.");
    } finally {
      setSending(false);
    }
  };

  const startNewChat = () => {
    setConversationId(null);
    setMessages([]);
    setError("");
  };

  return (
    <div className="fixed bottom-5 right-4 z-50 sm:bottom-6 sm:right-6">
      {open && (
        <section
          aria-label="Marble AI Smart Chatbot"
          className="mb-3 flex h-[min(34rem,calc(100dvh-7rem))] w-[min(24rem,calc(100vw-2rem))] flex-col overflow-hidden border border-stone-200 bg-white shadow-2xl"
        >
          <header className="flex items-center justify-between bg-stone-900 px-4 py-3 text-white">
            <div className="flex items-center gap-3">
              <span className="grid size-9 place-items-center bg-white/10">
                <Sparkles size={18} aria-hidden="true" />
              </span>
              <div>
                <h2 className="text-sm font-semibold">Marble AI Assistant</h2>
                <p className="text-xs text-stone-300">Catalog-aware assistance</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={startNewChat}
                aria-label="Start a new conversation"
                title="New conversation"
                className="p-2 text-stone-300 transition hover:bg-white/10 hover:text-white"
              >
                <RotateCcw size={16} aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close chatbot"
                className="p-2 text-stone-300 transition hover:bg-white/10 hover:text-white"
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto bg-stone-50 p-4" aria-live="polite">
            {messages.length === 0 && !loadingHistory && (
              <div className="border border-stone-200 bg-white p-3 text-sm text-stone-700">
                <p className="font-medium">How can I help?</p>
                <p className="mt-1 text-stone-500">You can ask me about products, availability, or anything else related to our catalog.</p>
              </div>
            )}
            {loadingHistory && (
              <p className="flex items-center gap-2 text-sm text-stone-500">
                <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
                Loading conversation…
              </p>
            )}
            {messages.map((message) => (
              <div
                key={message.id}
                className={`max-w-[90%] whitespace-pre-wrap break-words px-3 py-2 text-sm ${
                  message.role === "user"
                    ? "ml-auto bg-stone-900 text-white"
                    : "mr-auto border border-stone-200 bg-white text-stone-800"
                }`}
              >
                {message.content}
              </div>
            ))}
            {sending && (
              <p className="flex items-center gap-2 text-sm text-stone-500" role="status">
                <LoaderCircle size={16} className="animate-spin" aria-hidden="true" />
                Thinking…
              </p>
            )}
            {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
            <div ref={endRef} />
          </div>

          <div className="border-t border-stone-200 bg-white p-3">
            <p className="mb-2 text-[11px] text-stone-500">
              Read-only assistance. No orders, quotations, or inventory will be changed.
              Mistakes may occur. Please verify any information provided by the AI.
            </p>
            <form onSubmit={sendMessage} className="flex items-end gap-2">
              <label htmlFor="chatbot-message" className="sr-only">Your message</label>
              <textarea
                id="chatbot-message"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                maxLength={2000}
                rows={1}
                placeholder="Ask Marble AI…"
                className="max-h-28 min-h-10 flex-1 resize-y border border-stone-300 px-3 py-2 text-sm text-stone-900 outline-none focus:border-stone-600"
              />
              <button
                type="submit"
                disabled={!draft.trim() || sending || loadingHistory}
                aria-label="Send message"
                className="grid size-10 shrink-0 place-items-center bg-stone-900 text-white transition hover:bg-stone-700 disabled:cursor-not-allowed disabled:bg-stone-300"
              >
                {sending
                  ? <LoaderCircle size={17} className="animate-spin" aria-hidden="true" />
                  : <Send size={17} aria-hidden="true" />}
              </button>
            </form>
          </div>
        </section>
      )}
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-label={open ? "Close Marble AI chatbot" : "Open Marble AI chatbot"}
        aria-expanded={open}
        className="ml-auto flex items-center gap-2 bg-stone-900 px-4 py-3 text-sm font-medium text-white shadow-lg transition hover:bg-stone-700"
      >
        {open ? <X size={18} aria-hidden="true" /> : <Bot size={19} aria-hidden="true" />}
        <span>{open ? "Close" : "Ask Marble AI"}</span>
      </button>
    </div>
  );
}
