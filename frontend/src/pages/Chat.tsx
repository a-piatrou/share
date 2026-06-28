/**
 * Chat page — public RAG chatbot widget.
 * Route: /
 * Calls: POST /chat/query (no auth — public endpoint)
 * Renders: grounded answer, citations (source_id + snippet), ABSTAIN state.
 * REQ-003, REQ-005, REQ-006, AC-5 (explainability via citations).
 */
import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { postChatQuery, ApiError } from "@/api/client";
import { CitationList } from "@/components/CitationList";
import type { RAGAnswer } from "@/api/schemas";

const formSchema = z.object({
  query: z.string().min(1, "Please enter a question"),
});
type FormValues = z.infer<typeof formSchema>;

interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  answer?: RAGAnswer;
  traceId?: string | null;
  error?: string;
  timestamp: Date;
}

function IntentBadge({ intent }: { intent: RAGAnswer["intent"] }) {
  const map = {
    client: { label: "Client Query", cls: "gw-badge-teal" },
    candidate: { label: "Candidate Query", cls: "gw-badge-amber" },
    unknown: { label: "Unknown Intent", cls: "gw-badge-muted" },
  };
  const { label, cls } = map[intent];
  return <span className={`gw-badge ${cls}`}>{label}</span>;
}

function ConfidenceBar({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 70 ? "bg-gw-green" : pct >= 40 ? "bg-gw-amber" : "bg-gw-crimson";
  return (
    <div className="flex items-center gap-2 mt-1">
      <span className="text-2xs text-gw-subtle">Confidence</span>
      <div className="flex-1 max-w-24 h-1 bg-gw-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-2xs font-mono text-gw-subtle">{pct}%</span>
    </div>
  );
}

function AssistantMessage({ msg }: { msg: Message }) {
  const { answer } = msg;

  if (msg.error) {
    return (
      <div className="gw-card border-gw-crimson/40 bg-red-950/20">
        <p className="text-sm text-red-400">{msg.error}</p>
      </div>
    );
  }

  if (!answer) return null;

  return (
    <div className={`gw-card ${answer.abstained ? "border-amber-700/50 bg-amber-950/10" : ""}`}>
      {/* Abstain banner — REQ-005 */}
      {answer.abstained && (
        <div className="flex items-center gap-2 mb-3 px-3 py-2 bg-amber-900/30 rounded-lg border border-amber-700/40">
          <svg className="w-4 h-4 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <div>
            <p className="text-xs font-semibold text-amber-400">Insufficient Grounding — Abstaining</p>
            <p className="text-2xs text-amber-600 mt-0.5">
              Context below confidence threshold. No answer generated to prevent hallucination.
            </p>
          </div>
        </div>
      )}

      {/* Answer text */}
      <p className="text-sm text-gw-text leading-relaxed whitespace-pre-wrap">{answer.answer}</p>

      {/* Meta row */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        <IntentBadge intent={answer.intent} />
        <ConfidenceBar confidence={answer.confidence} />
        {msg.traceId && (
          <span className="font-mono text-2xs text-gw-subtle ml-auto">
            trace: {msg.traceId}
          </span>
        )}
      </div>

      {/* Citations — AC-5 explainability */}
      {!answer.abstained && answer.citations.length > 0 && (
        <CitationList citations={answer.citations} />
      )}

      {!answer.abstained && answer.citations.length === 0 && (
        <p className="mt-3 text-2xs text-gw-subtle italic">No citations returned for this answer.</p>
      )}
    </div>
  );
}

export function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionId] = useState(() => crypto.randomUUID());
  const bottomRef = useRef<HTMLDivElement>(null);

  const { register, handleSubmit, reset, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
  });

  const mutation = useMutation({
    mutationFn: (query: string) =>
      postChatQuery({ query, session_id: sessionId }),
    onSuccess: ({ data, traceId }, query) => {
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "user",
          text: query,
          timestamp: new Date(),
        },
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: data.answer,
          answer: data,
          traceId,
          timestamp: new Date(),
        },
      ]);
    },
    onError: (err, query) => {
      const msg = err instanceof ApiError ? `${err.message}${err.detail ? ` — ${err.detail}` : ""}` : "Unexpected error";
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "user",
          text: query,
          timestamp: new Date(),
        },
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: "",
          error: msg,
          timestamp: new Date(),
        },
      ]);
    },
  });

  const onSubmit = ({ query }: FormValues) => {
    reset();
    mutation.mutate(query);
  };

  // Scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col h-[calc(100vh-10rem)] max-w-3xl mx-auto">
      {/* Page header */}
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gw-text">Intelligence Chat</h1>
        <p className="text-sm text-gw-subtle mt-1">
          Grounded answers only — abstains when context is insufficient. Every answer cites its sources.
        </p>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <div className="w-12 h-12 rounded-2xl bg-gw-teal-dim flex items-center justify-center">
              <svg className="w-6 h-6 text-gw-teal" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
            </div>
            <p className="text-gw-subtle text-sm max-w-xs">
              Ask about our company, open roles, or capabilities. Answers are grounded in retrieved context only.
            </p>
          </div>
        )}

        {messages.map((msg) =>
          msg.role === "user" ? (
            <div key={msg.id} className="flex justify-end">
              <div className="max-w-[75%] px-4 py-2.5 bg-gw-teal-dim rounded-xl rounded-br-sm">
                <p className="text-sm text-gw-text">{msg.text}</p>
              </div>
            </div>
          ) : (
            <div key={msg.id} className="max-w-[90%]">
              <AssistantMessage msg={msg} />
            </div>
          )
        )}

        {mutation.isPending && (
          <div className="max-w-[90%]">
            <div className="gw-card">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-gw-teal animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-gw-teal animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-gw-teal animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
                <span className="text-xs text-gw-subtle">Retrieving context and grounding answer…</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <form onSubmit={handleSubmit(onSubmit)} className="mt-4 flex gap-2 items-end">
        <div className="flex-1">
          <textarea
            {...register("query")}
            className="gw-textarea text-sm min-h-[44px] max-h-36"
            placeholder="Ask about capabilities, open roles, case studies…"
            rows={1}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(onSubmit)();
              }
            }}
          />
          {errors.query && (
            <p className="text-2xs text-red-400 mt-1">{errors.query.message}</p>
          )}
        </div>
        <button
          type="submit"
          className="gw-btn-primary h-11"
          disabled={mutation.isPending}
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
          Send
        </button>
      </form>
    </div>
  );
}
