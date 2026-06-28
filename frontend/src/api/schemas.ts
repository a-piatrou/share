/**
 * Zod schemas mirroring the frozen OpenAPI contract (contract_version 1).
 * Every shape here must match system/contracts/openapi.yaml exactly.
 * Do NOT loosen additionalProperties — the contract enforces strict shapes.
 */
import { z } from "zod";

// ── Shared primitives ────────────────────────────────────────────────────────

export const EvidenceRefSchema = z.object({
  review_id: z.string(),
  quote: z.string(),
});
export type EvidenceRef = z.infer<typeof EvidenceRefSchema>;

export const EvidencedItemSchema = z.object({
  text: z.string(),
  evidence_ref: EvidenceRefSchema,
});
export type EvidencedItem = z.infer<typeof EvidencedItemSchema>;

// ── /chat/query ──────────────────────────────────────────────────────────────

export const ChatQueryRequestSchema = z.object({
  query: z.string().min(1),
  session_id: z.string().optional(),
});
export type ChatQueryRequest = z.infer<typeof ChatQueryRequestSchema>;

export const CitationSchema = z.object({
  source_id: z.string(),
  snippet: z.string(),
});
export type Citation = z.infer<typeof CitationSchema>;

export const RAGAnswerSchema = z.object({
  answer: z.string(),
  citations: z.array(CitationSchema),
  intent: z.enum(["client", "candidate", "unknown"]),
  confidence: z.number(),
  abstained: z.boolean(),
});
export type RAGAnswer = z.infer<typeof RAGAnswerSchema>;

// ── /feedback/analyze ────────────────────────────────────────────────────────

export const ReviewKindSchema = z.enum(["peer", "manager", "self"]);
export type ReviewKind = z.infer<typeof ReviewKindSchema>;

export const ReviewSchema = z.object({
  review_id: z.string(),
  kind: ReviewKindSchema,
  text: z.string().min(1),
});
export type Review = z.infer<typeof ReviewSchema>;

export const FeedbackAnalyzeRequestSchema = z.object({
  employee_id: z.string().min(1),
  reviews: z.array(ReviewSchema).min(1),
});
export type FeedbackAnalyzeRequest = z.infer<typeof FeedbackAnalyzeRequestSchema>;

export const RiskItemSchema = z.object({
  type: z.enum(["burnout", "conflict", "attrition", "performance", "other"]),
  text: z.string(),
  severity: z.enum(["low", "medium", "high"]),
  evidence_ref: EvidenceRefSchema,
});
export type RiskItem = z.infer<typeof RiskItemSchema>;

export const FeedbackAnalysisSchema = z.object({
  analysis_id: z.string(),
  employee_id: z.string(),
  feedback_score: z.number(),   // [0,1]
  sentiment: z.number(),        // [-1,1]
  strengths: z.array(EvidencedItemSchema),
  weaknesses: z.array(EvidencedItemSchema),
  risks: z.array(RiskItemSchema),
  team_dynamics_signals: z.array(EvidencedItemSchema),
  confidence_score: z.number(), // [0,1]
});
export type FeedbackAnalysis = z.infer<typeof FeedbackAnalysisSchema>;

// ── /team/assemble ───────────────────────────────────────────────────────────

export const TeamAssembleRequestSchema = z.object({
  project_description: z.string().min(1),
  requirements: z.array(z.string()).optional(),
  constraints: z
    .object({
      timeline: z.string().optional(),
      budget: z.string().optional(),
      timezone: z.string().optional(),
    })
    .optional(),
});
export type TeamAssembleRequest = z.infer<typeof TeamAssembleRequestSchema>;

export const FeedbackSignalRefSchema = z.object({
  source: z.string(),
  signal: z.string(),
});
export type FeedbackSignalRef = z.infer<typeof FeedbackSignalRefSchema>;

export const TeamMemberSchema = z.object({
  employee_id: z.string(),
  role: z.string(),
  match_score: z.number(),     // [0,1]
  feedback_signal_ref: FeedbackSignalRefSchema,
  rationale: z.string(),
});
export type TeamMember = z.infer<typeof TeamMemberSchema>;

export const GapSchema = z.object({
  skill: z.string(),
  severity: z.enum(["low", "medium", "high"]),
});
export type Gap = z.infer<typeof GapSchema>;

export const AssemblyRiskSchema = z.object({
  text: z.string(),
  severity: z.enum(["low", "medium", "high"]),
});
export type AssemblyRisk = z.infer<typeof AssemblyRiskSchema>;

export const AlternativeSchema = z.object({
  employee_id: z.string(),
  role: z.string(),
  match_score: z.number(),
});
export type Alternative = z.infer<typeof AlternativeSchema>;

export const TeamAssemblySchema = z.object({
  team: z.array(TeamMemberSchema),
  gaps: z.array(GapSchema),
  risks: z.array(AssemblyRiskSchema),
  alternatives: z.array(AlternativeSchema),
  rationale: z.string(),
});
export type TeamAssembly = z.infer<typeof TeamAssemblySchema>;

// ── /health ───────────────────────────────────────────────────────────────────

export const HealthSchema = z.object({
  status: z.enum(["ok"]),
  version: z.string().optional(),
});
export type Health = z.infer<typeof HealthSchema>;
