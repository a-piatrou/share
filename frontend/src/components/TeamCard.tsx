/**
 * TeamCard — displays a single assembled team member with full explainability:
 *   - match_score, role, rationale, feedback_signal_ref (source + signal)
 * Satisfies REQ-014 / AC-5 / AC-3 visibility.
 */
import type { TeamMember } from "@/api/schemas";

interface Props {
  member: TeamMember;
  rank: number;
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const color =
    pct >= 80 ? "bg-gw-green" : pct >= 60 ? "bg-gw-teal" : pct >= 40 ? "bg-gw-amber" : "bg-gw-crimson";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-gw-muted rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs font-mono text-gw-text w-9 text-right">{pct}%</span>
    </div>
  );
}

export function TeamCard({ member, rank }: Props) {
  return (
    <div className="gw-card flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="text-2xs font-mono text-gw-subtle">#{rank}</span>
          <h3 className="text-base font-semibold text-gw-text mt-0.5">{member.employee_id}</h3>
          <span className="gw-badge-teal mt-1">{member.role}</span>
        </div>
        <div className="text-right">
          <p className="text-2xs text-gw-subtle mb-1">Match Score</p>
          <div className="w-28">
            <ScoreBar score={member.match_score} />
          </div>
        </div>
      </div>

      {/* Rationale — explainability */}
      <div>
        <p className="gw-section-title">Rationale</p>
        <p className="text-sm text-gw-subtle leading-relaxed">{member.rationale}</p>
      </div>

      {/* Feedback signal ref — AC-3 explainability */}
      <div className="border-t border-gw-border pt-3">
        <p className="gw-section-title">Feedback Signal</p>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-2xs text-gw-subtle w-14 shrink-0">Source</span>
            <span className="font-mono text-2xs text-gw-teal break-all">
              {member.feedback_signal_ref.source}
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-2xs text-gw-subtle w-14 shrink-0 mt-0.5">Signal</span>
            <span className="text-xs text-gw-text leading-relaxed">
              {member.feedback_signal_ref.signal}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
