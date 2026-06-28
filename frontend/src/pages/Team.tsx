/**
 * Team Assembly UI — internal page (RBAC).
 * Route: /team
 * Calls: POST /team/assemble
 * Renders: team grid with match_score, role, rationale, feedback_signal_ref (AC-3/AC-5);
 *          gaps, risks, alternatives, overall rationale.
 * REQ-008, REQ-009, AC-3, AC-5.
 */
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { postTeamAssemble, ApiError } from "@/api/client";
import { TeamCard } from "@/components/TeamCard";
import { TokenGate } from "@/components/TokenGate";
import { useAuth } from "@/hooks/useAuth";
import type { TeamAssembly } from "@/api/schemas";

// ── Form schema ───────────────────────────────────────────────────────────────

const formSchema = z.object({
  project_description: z.string().min(10, "Description too short"),
  requirements: z.array(z.object({ value: z.string().min(1) })).optional(),
  constraints: z.object({
    timeline: z.string().optional(),
    budget: z.string().optional(),
    timezone: z.string().optional(),
  }).optional(),
});

type FormValues = z.infer<typeof formSchema>;

// ── Severity badge ────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: "low" | "medium" | "high" }) {
  const cls =
    severity === "high"
      ? "gw-badge-crimson"
      : severity === "medium"
        ? "gw-badge-amber"
        : "gw-badge-green";
  return <span className={`gw-badge ${cls}`}>{severity}</span>;
}

// ── Assembly result ───────────────────────────────────────────────────────────

function AssemblyResult({ result, traceId }: { result: TeamAssembly; traceId: string | null }) {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-gw-text">Assembled Team</h2>
          {traceId && (
            <p className="text-2xs text-gw-subtle font-mono mt-0.5">trace: {traceId}</p>
          )}
        </div>
        <span className="gw-badge-teal">{result.team.length} members</span>
      </div>

      {/* Overall rationale — AC-5 */}
      <div className="gw-card">
        <p className="gw-section-title">Assembly Rationale</p>
        <p className="text-sm text-gw-subtle leading-relaxed">{result.rationale}</p>
      </div>

      {/* Team grid — each card shows feedback_signal_ref (AC-3) + rationale (AC-5) */}
      <div>
        <p className="gw-section-title">Team Members</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {result.team.map((member, i) => (
            <TeamCard key={member.employee_id} member={member} rank={i + 1} />
          ))}
        </div>
      </div>

      {/* Gaps */}
      {result.gaps.length > 0 && (
        <div>
          <p className="gw-section-title text-gw-amber">Skill Gaps ({result.gaps.length})</p>
          <div className="overflow-x-auto rounded-lg border border-gw-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gw-border bg-gw-muted/40">
                  <th className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle">Skill</th>
                  <th className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle">Severity</th>
                </tr>
              </thead>
              <tbody>
                {result.gaps.map((gap, idx) => (
                  <tr key={gap.skill} className={idx % 2 === 0 ? "bg-gw-surface" : "bg-gw-bg"}>
                    <td className="px-3 py-2 text-gw-text">{gap.skill}</td>
                    <td className="px-3 py-2">
                      <SeverityBadge severity={gap.severity} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Risks */}
      {result.risks.length > 0 && (
        <div>
          <p className="gw-section-title text-gw-crimson">Assembly Risks ({result.risks.length})</p>
          <div className="space-y-2">
            {result.risks.map((risk, idx) => (
              <div
                key={idx}
                className="flex items-start gap-3 px-3 py-2.5 rounded-lg border border-gw-border bg-gw-surface"
              >
                <SeverityBadge severity={risk.severity} />
                <p className="text-sm text-gw-subtle leading-relaxed">{risk.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Alternatives */}
      {result.alternatives.length > 0 && (
        <div>
          <p className="gw-section-title">Alternative Candidates</p>
          <div className="overflow-x-auto rounded-lg border border-gw-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gw-border bg-gw-muted/40">
                  <th className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle">Employee</th>
                  <th className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle">Role</th>
                  <th className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle">Match Score</th>
                </tr>
              </thead>
              <tbody>
                {result.alternatives.map((alt, idx) => (
                  <tr key={alt.employee_id} className={idx % 2 === 0 ? "bg-gw-surface" : "bg-gw-bg"}>
                    <td className="px-3 py-2 font-mono text-gw-teal text-sm">{alt.employee_id}</td>
                    <td className="px-3 py-2 text-gw-text">{alt.role}</td>
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1 bg-gw-muted rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gw-teal rounded-full"
                            style={{ width: `${Math.round(alt.match_score * 100)}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-gw-subtle">
                          {Math.round(alt.match_score * 100)}%
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

function TeamForm({ token }: { token: string }) {
  const [result, setResult] = useState<{ data: TeamAssembly; traceId: string | null } | null>(null);

  const { register, control, handleSubmit, formState: { errors } } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      project_description: "",
      requirements: [],
      constraints: { timeline: "", budget: "", timezone: "" },
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: "requirements" });

  const mutation = useMutation({
    mutationFn: (values: FormValues) => {
      // Map form shape to API shape: filter blank constraints, unwrap requirement objects
      const requirements = (values.requirements ?? [])
        .map((r) => r.value)
        .filter(Boolean);

      const rawConstraints = values.constraints ?? {};
      const constraints: Record<string, string> = {};
      if (rawConstraints.timeline?.trim()) constraints["timeline"] = rawConstraints.timeline.trim();
      if (rawConstraints.budget?.trim()) constraints["budget"] = rawConstraints.budget.trim();
      if (rawConstraints.timezone?.trim()) constraints["timezone"] = rawConstraints.timezone.trim();

      return postTeamAssemble(
        {
          project_description: values.project_description,
          requirements: requirements.length ? requirements : undefined,
          constraints: Object.keys(constraints).length ? constraints : undefined,
        },
        token,
      );
    },
    onSuccess: (res) => setResult(res),
  });

  const onSubmit = (values: FormValues) => mutation.mutate(values);

  return (
    <div className="space-y-8">
      <form onSubmit={handleSubmit(onSubmit)} className="gw-card space-y-5">
        <h2 className="text-base font-semibold text-gw-text">Assemble a Team</h2>

        {/* Project description */}
        <div>
          <label className="gw-label" htmlFor="project_description">Project Description</label>
          <textarea
            id="project_description"
            className="gw-textarea text-sm"
            rows={4}
            placeholder="Describe the project, its goals, and the kind of team you need…"
            {...register("project_description")}
          />
          {errors.project_description && (
            <p className="mt-1 text-xs text-red-400">{errors.project_description.message}</p>
          )}
        </div>

        {/* Requirements */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="gw-label mb-0">Requirements (optional)</label>
            <button
              type="button"
              className="gw-btn-secondary text-xs py-1 px-2"
              onClick={() => append({ value: "" })}
            >
              + Add
            </button>
          </div>
          {fields.map((field, idx) => (
            <div key={field.id} className="flex gap-2 mb-2">
              <input
                className="gw-input text-sm"
                placeholder={`Requirement ${idx + 1}`}
                {...register(`requirements.${idx}.value`)}
              />
              <button
                type="button"
                className="text-gw-subtle hover:text-red-400 text-xs px-2"
                onClick={() => remove(idx)}
              >
                ✕
              </button>
            </div>
          ))}
        </div>

        {/* Constraints */}
        <div>
          <label className="gw-label">Constraints (optional)</label>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="text-2xs text-gw-subtle mb-1 block">Timeline</label>
              <input className="gw-input text-sm" placeholder="e.g. 3 months" {...register("constraints.timeline")} />
            </div>
            <div>
              <label className="text-2xs text-gw-subtle mb-1 block">Budget</label>
              <input className="gw-input text-sm" placeholder="e.g. $50k" {...register("constraints.budget")} />
            </div>
            <div>
              <label className="text-2xs text-gw-subtle mb-1 block">Timezone</label>
              <input className="gw-input text-sm" placeholder="e.g. UTC+0" {...register("constraints.timezone")} />
            </div>
          </div>
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
          {mutation.isPending ? "Assembling…" : "Assemble Team"}
        </button>
      </form>

      {result && (
        <div className="gw-card">
          <AssemblyResult result={result.data} traceId={result.traceId} />
        </div>
      )}
    </div>
  );
}

export function TeamPage() {
  const { token, setToken } = useAuth();

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-gw-text">Team Assembler</h1>
        <p className="text-sm text-gw-subtle mt-1">
          Internal · RBAC-protected · Each member shows the behavioral signal that drove their selection.
        </p>
      </div>

      <TokenGate token={token} onSetToken={setToken}>
        <TeamForm token={token} />
      </TokenGate>
    </div>
  );
}
