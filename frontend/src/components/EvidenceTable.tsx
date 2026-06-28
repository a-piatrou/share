/**
 * EvidenceTable — renders EvidencedItem[] or RiskItem[] with their evidence_ref.
 * Used in the Feedback Dashboard. Satisfies REQ-014 / AC-5 (explainability).
 */
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";
import type { EvidencedItem, RiskItem } from "@/api/schemas";

// ── EvidencedItems table ─────────────────────────────────────────────────────

const evidencedHelper = createColumnHelper<EvidencedItem>();

const evidencedColumns = [
  evidencedHelper.accessor("text", {
    header: "Finding",
    cell: (info) => (
      <span className="text-sm text-gw-text">{info.getValue()}</span>
    ),
  }),
  evidencedHelper.accessor("evidence_ref.review_id", {
    header: "Review",
    cell: (info) => (
      <span className="font-mono text-2xs text-gw-teal">{info.getValue()}</span>
    ),
  }),
  evidencedHelper.accessor("evidence_ref.quote", {
    header: "Verbatim Quote",
    cell: (info) => (
      <span className="text-xs text-gw-subtle italic">
        &ldquo;{info.getValue()}&rdquo;
      </span>
    ),
  }),
];

interface EvidencedTableProps {
  data: EvidencedItem[];
  emptyText?: string;
}

export function EvidencedItemsTable({ data, emptyText = "None" }: EvidencedTableProps) {
  const table = useReactTable({
    data,
    columns: evidencedColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (data.length === 0) {
    return <p className="text-sm text-gw-subtle italic">{emptyText}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gw-border">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-gw-border bg-gw-muted/40">
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, idx) => (
            <tr
              key={row.id}
              className={idx % 2 === 0 ? "bg-gw-surface" : "bg-gw-bg"}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2.5 align-top">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Risks table ──────────────────────────────────────────────────────────────

const riskHelper = createColumnHelper<RiskItem>();

const riskColumns = [
  riskHelper.accessor("type", {
    header: "Type",
    cell: (info) => (
      <span className="gw-badge-muted font-mono">{info.getValue()}</span>
    ),
  }),
  riskHelper.accessor("severity", {
    header: "Severity",
    cell: (info) => {
      const v = info.getValue();
      const cls =
        v === "high"
          ? "gw-badge-crimson"
          : v === "medium"
            ? "gw-badge-amber"
            : "gw-badge-green";
      return <span className={`gw-badge ${cls}`}>{v}</span>;
    },
  }),
  riskHelper.accessor("text", {
    header: "Description",
    cell: (info) => (
      <span className="text-sm text-gw-text">{info.getValue()}</span>
    ),
  }),
  riskHelper.accessor("evidence_ref.review_id", {
    header: "Review",
    cell: (info) => (
      <span className="font-mono text-2xs text-gw-teal">{info.getValue()}</span>
    ),
  }),
  riskHelper.accessor("evidence_ref.quote", {
    header: "Verbatim Quote",
    cell: (info) => (
      <span className="text-xs text-gw-subtle italic">
        &ldquo;{info.getValue()}&rdquo;
      </span>
    ),
  }),
];

interface RisksTableProps {
  data: RiskItem[];
  emptyText?: string;
}

export function RisksTable({ data, emptyText = "No risks identified" }: RisksTableProps) {
  const table = useReactTable({
    data,
    columns: riskColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  if (data.length === 0) {
    return <p className="text-sm text-gw-subtle italic">{emptyText}</p>;
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-gw-border">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-gw-border bg-gw-muted/40">
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  className="px-3 py-2 text-left text-2xs font-mono uppercase tracking-wider text-gw-subtle"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, idx) => (
            <tr
              key={row.id}
              className={idx % 2 === 0 ? "bg-gw-surface" : "bg-gw-bg"}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id} className="px-3 py-2.5 align-top">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
