/**
 * CitationList — renders RAG grounding citations (source_id + snippet).
 * Satisfies REQ-014 / AC-5: every RAG answer must expose its why.
 */
import type { Citation } from "@/api/schemas";

interface Props {
  citations: Citation[];
}

export function CitationList({ citations }: Props) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-4">
      <p className="gw-section-title">Sources</p>
      <ol className="space-y-2">
        {citations.map((c, i) => (
          <li key={c.source_id} className="flex gap-3">
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gw-muted text-gw-subtle text-2xs font-mono flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <div className="flex-1 min-w-0">
              <span className="font-mono text-2xs text-gw-teal break-all">{c.source_id}</span>
              <p className="mt-0.5 text-sm text-gw-subtle leading-relaxed line-clamp-4">
                &ldquo;{c.snippet}&rdquo;
              </p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
