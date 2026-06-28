/**
 * Feedback Dashboard — internal page (RBAC).
 * Route: /feedback
 * Calls: POST /feedback/analyze
 * Renders: strengths, weaknesses, risks, team_dynamics_signals — each with evidence_ref.
 * REQ-007, AC-2, AC-5.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { postFeedbackAnalyze, ApiError } from "@/api/client";
import { EvidencedItemsTable, RisksTable } from "@/components/EvidenceTable";
import { TokenGate } from "@/components/TokenGate";
import { useAuth } from "@/hooks/useAuth";
import type { FeedbackAnalysis } from "@/api/schemas";

// ── Form schema ───────────────────────────────────────────────────────────────

const reviewSchema = z.object({
  review_id: z.string().min(1, "Review ID required"),
  kind: z.enum(["peer", "manager", "self"]),
  text: z.string().min(10, "Review text too short"),
});

const formSchema = z.object({
  employee_id: z.string().min(1, "Employee ID required"),
  reviews: z.array(reviewSchema).min(1, "At least one review required"),
});

type FormValues = z.infer<typeof formSchema>;

// ── Subcomponents ─────────────────────────────────────────────────────────────

function ScorePill({ label, value, range }: { label: string; value: number; range: [number, number] }) {
  const [min, max] = range;
  const pct = ((value - min) / (max - min)) * 100;
  const color = pct >= 70 ? "text-gw-green" : pct >= 40 ? "text-gw-amber" : "text-gw-crimson";
  return (
    <div className="gw-card flex flex-col items-center justify-center gap-1 min-w-[110px]">
      <span className="text-2xs text-gw-subtle uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-bold font-mono ${color}`}>{value.toFixed(2)}</span>
    </div>
  );
}

function AnalysisResult({ result, traceId }: { result: FeedbackAnalysis; traceId: string | null }) {
  const sentimentLabel =
    result.sentiment > 0.3 ? "Positive" : result.sentiment < -0.3 ? "Negative" : "Neutral";
  const sentimentColor =
    result.sentiment > 0.3 ? "gw-badge-green" : result.sentiment < -0.3 ? "gw-badge-crimson" : "gw-badge-muted";

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gw-text">
            Analysis: <span className="font-mono text-gw-teal">{result.employee_id}</span>
          </h2>
          <p className="text-xs text-gw-subtle font-mono mt-0.5">
            analysis_id: {result.analysis_id}
          </p>
          {traceId && (
            <p className="text-2xs text-gw-subtle font-mono">trace: {traceId}</p>
          )}
        </div>
        <div className="flex gap-3 flex-wrap">
          <ScorePill label="Feedback Score" value={result.feedback_score} range={[0, 1]} />
          <ScorePill label="Confidence" value={result.confidence_score} range={[0, 1]} />
          <div className="gw-card flex flex-col items-center justify-center gap-1 min-w-[110px]">
            <span className="text-2xs text-gw-subtle uppercase tracking-wider">Sentiment</span>
            <span className={`gw-badge ${sentimentColor} text-sm mt-1`}>{sentimentLabel}</span>
            <span className="text-xs font-mono text-gw-subtle">{result.sentiment.toFixed(2)}</span>
          </div>
        </div>
      </div>

      {/* Strengths */}
      <div>
        <p className="gw-section-title text-gw-green">Strengths ({result.strengths.length})</p>
        <EvidencedItemsTable data={result.strengths} emptyText="No strengths identified" />
      </div>

      {/* Weaknesses */}
      <div>
        <p className="gw-section-title text-gw-amber">Weaknesses ({result.weaknesses.length})</p>
        <EvidencedItemsTable data={result.weaknesses} emptyText="No weaknesses identified" />
      </div>

      {/* Risks */}
      <div>
        <p className="gw-section-title text-gw-crimson">Risks ({result.risks.length})</p>
        <RisksTable data={result.risks} />
      </div>

      {/* Team dynamics signals */}
      <div>
        <p className="gw-section-title text-gw-teal">Team Dynamics Signals ({result.team_dynamics_signals.length})</p>
        <EvidencedItemsTable data={result.team_dynamics_signals} emptyText="No dynamics signals detected" />
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

function FeedbackForm({ token }: { token: string }) {
  const [result, setResult] = useState<{ data: FeedbackAnalysis; traceId: string | null } | null>(null);

  const { register, control, handleSubmit, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      employee_id: "",
      reviews: [{ review_id: "", kind: "peer", text: "" }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "reviews" });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => postFeedbackAnalyze(values, token),
    onSuccess: (res) => setResult(res),
  });

  const onSubmit = (values: FormValues) => mutation.mutate(values);

  return (
    <div className="space-y-8">
      {/* Form */}
      <form onSubmit={handleSubmit(onSubmit)} className="gw-card space-y-5">
        <h2 className="text-base font-semibold text-gw-text">Submit Feedback Reviews</h2>

        <div>
          <label className="gw-label" htmlFor="employee_id">Employee ID</label>
          <input
            id="employee_id"
            className="gw-input max-w-xs font-mono"
            placeholder="E001"
            {...register("employee_id")}
          />
          {errors.employee_id && (
            <p className="mt-1 text-xs text-red-400">{errors.employee_id.message}</p>
          )}
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="gw-label mb-0">Reviews</label>
            <button
              type="button"
              className="gw-btn-secondary text-xs py-1 px-2"
              onClick={() => append({ review_id: "", kind: "peer", text: "" })}
            >
              + Add Review
            </button>
          </div>

          {fields.map((field, idx) => (
            <div key={field.id} className="bg-gw-bg rounded-lg border border-gw-border p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono text-gw-subtle">Review #{idx + 1}</span>
                {fields.length > 1 && (
                  <button
                    type="button"
                    className="text-2xs text-red-400 hover:text-red-300"
                    onClick={() => remove(idx)}
                  >
                    Remove
                  </button>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="gw-label">Review ID</label>
                  <input
                    className="gw-input font-mono text-sm"
                    placeholder="R001"
                    {...register(`reviews.${idx}.review_id`)}
                  />
                  {errors.reviews?.[idx]?.review_id && (
                    <p className="mt-1 text-xs text-red-400">{errors.reviews[idx]?.review_id?.message}</p>
                  )}
                </div>
                <div>
                  <label className="gw-label">Kind</label>
                  <select className="gw-input text-sm" {...register(`reviews.${idx}.kind`)}>
                    <option value="peer">Peer</option>
                    <option value="manager">Manager</option>
                    <option value="self">Self</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="gw-label">Review Text</label>
                <textarea
                  className="gw-textarea text-sm"
                  rows={3}
                  placeholder="Enter review text…"
                  {...register(`reviews.${idx}.text`)}
                />
                {errors.reviews?.[idx]?.text && (
                  <p className="mt-1 text-xs text-red-400">{errors.reviews[idx]?.text?.message}</p>
                )}
              </div>
            </div>
          ))}

          {errors.reviews?.root && (
            <p className="text-xs text-red-400">{errors.reviews.root.message}</p>
          )}
        </div>

        {mutation.isError && (
          <div className="px-3 py-2 bg-red-950/30 border border-red-900/50 rounded-lg">
            <p className="text-sm text-red-400">
              {mutation.error instanceof ApiError
                ? `${mutation.error.message}${mutation.error.detail ? `: ${mutation.error.detail}` : ""}`
                : "Unexpected error"}
            </p>
          </div>
        )}

        <button type="submit" className="gw-btn-primary" disabled={mutation.isPending}>
          {mutation.isPending ? "Analyzing…" : "Analyze Feedback"}
        </button>
      </form>

      {/* Result */}
      {result && (
        <div className="gw-card">
          <AnalysisResult result={result.data} traceId={result.traceId} />
        </div>
      )}
    </div>
  );
}

export function FeedbackPage() {
  const { token, setToken } = useAuth();

  return (
    <div className="max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gw-text">Feedback Intelligence</h1>
        <p className="text-sm text-gw-subtle mt-1">
          Internal · RBAC-protected · Every finding cites a verbatim quote from the source review.
        </p>
      </div>

      <TokenGate token={token} onSetToken={setToken}>
        <FeedbackForm token={token} />
      </TokenGate>
    </div>
  );
}
