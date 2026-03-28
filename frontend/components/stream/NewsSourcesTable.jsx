"use client";
import { useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
} from "@tanstack/react-table";

const GOLD = "#FFB800";

const columnHelper = createColumnHelper();

function LiftBadge({ value }) {
  const n = parseFloat(value) || 0;
  const color = n >= 4 ? "#FF4081" : n >= 2.5 ? GOLD : "#4CAF50";
  return (
    <span
      className="px-1.5 py-0.5 text-[9px] font-mono font-bold"
      style={{ color, background: `${color}18`, border: `1px solid ${color}40` }}
    >
      {n.toFixed(2)}×
    </span>
  );
}

export default function NewsSourcesTable({ matches }) {
  const data = useMemo(() => (matches || []).slice(0, 30), [matches]);

  const columns = useMemo(() => [
    columnHelper.accessor("source", {
      header: "Domain",
      cell: info => (
        <span className="text-[10px] font-mono text-white/70">{info.getValue()}</span>
      ),
    }),
    columnHelper.accessor("headline", {
      header: "Headline",
      cell: info => (
        <span className="text-[10px] text-white/50 line-clamp-1">{info.getValue()}</span>
      ),
    }),
    columnHelper.accessor("similarity", {
      header: "Lift",
      cell: info => <LiftBadge value={info.getValue()} />,
      size: 64,
    }),
    columnHelper.accessor("url", {
      header: "Link",
      cell: info => info.getValue()
        ? (
          <a
            href={info.getValue()}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[9px] font-mono uppercase tracking-widest"
            style={{ color: GOLD, opacity: 0.7 }}
            onClick={e => e.stopPropagation()}
          >
            Visit ↗
          </a>
        )
        : <span className="text-white/15 text-[9px] font-mono">—</span>,
      size: 56,
    }),
  ], []);

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    initialState: { sorting: [{ id: "similarity", desc: true }] },
  });

  if (!data.length) {
    return (
      <p className="text-xs font-mono text-white/25 py-4 px-2">
        No news source matches found.
      </p>
    );
  }

  return (
    <div className="overflow-auto h-full">
      <table className="w-full border-collapse text-xs">
        <thead className="sticky top-0" style={{ background: "rgba(10,8,6,0.95)" }}>
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(header => (
                <th
                  key={header.id}
                  className="text-left py-2 px-2 text-[9px] font-mono uppercase tracking-widest border-b"
                  style={{ color: GOLD, borderColor: "rgba(255,184,0,0.15)", cursor: header.column.getCanSort() ? "pointer" : "default" }}
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {header.column.getIsSorted() === "asc" && " ↑"}
                  {header.column.getIsSorted() === "desc" && " ↓"}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row, i) => (
            <tr
              key={row.id}
              className="transition-colors"
              style={{ background: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)" }}
              onMouseEnter={e => e.currentTarget.style.background = "rgba(255,184,0,0.04)"}
              onMouseLeave={e => e.currentTarget.style.background = i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.015)"}
            >
              {row.getVisibleCells().map(cell => (
                <td
                  key={cell.id}
                  className="py-1.5 px-2 border-b"
                  style={{ borderColor: "rgba(255,255,255,0.04)" }}
                >
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
