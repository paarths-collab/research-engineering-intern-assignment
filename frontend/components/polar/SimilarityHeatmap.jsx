"use client";
import { useEffect, useState } from "react";
import { ResponsiveHeatMap } from "@nivo/heatmap";

const MOCK_DATA = [
  {
    id: "r/politics",
    data: [
      { x: "r/politics", y: 1.0 },
      { x: "r/worldnews", y: 0.72 },
      { x: "r/geopolitics", y: 0.41 },
      { x: "r/news", y: 0.65 },
      { x: "r/conspiracy", y: 0.18 },
    ],
  },
  {
    id: "r/worldnews",
    data: [
      { x: "r/politics", y: 0.72 },
      { x: "r/worldnews", y: 1.0 },
      { x: "r/geopolitics", y: 0.58 },
      { x: "r/news", y: 0.79 },
      { x: "r/conspiracy", y: 0.22 },
    ],
  },
  {
    id: "r/geopolitics",
    data: [
      { x: "r/politics", y: 0.41 },
      { x: "r/worldnews", y: 0.58 },
      { x: "r/geopolitics", y: 1.0 },
      { x: "r/news", y: 0.49 },
      { x: "r/conspiracy", y: 0.31 },
    ],
  },
  {
    id: "r/news",
    data: [
      { x: "r/politics", y: 0.65 },
      { x: "r/worldnews", y: 0.79 },
      { x: "r/geopolitics", y: 0.49 },
      { x: "r/news", y: 1.0 },
      { x: "r/conspiracy", y: 0.14 },
    ],
  },
  {
    id: "r/conspiracy",
    data: [
      { x: "r/politics", y: 0.18 },
      { x: "r/worldnews", y: 0.22 },
      { x: "r/geopolitics", y: 0.31 },
      { x: "r/news", y: 0.14 },
      { x: "r/conspiracy", y: 1.0 },
    ],
  },
];

export default function SimilarityHeatmap() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/similarity");
        const json = await res.json();
        setData(json);
      } catch {
        setData(MOCK_DATA);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="bg-[#0c0c0e] border border-[#1f1f23] rounded-none flex flex-col">
      {/* Header */}
      <div className="border-b border-[#1f1f23] px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-mono text-[#3b82f6] tracking-[0.2em] uppercase">
            Module 02
          </p>
          <h2 className="text-sm font-mono text-white tracking-widest uppercase mt-0.5">
            Subreddit Similarity Matrix
          </h2>
        </div>
        <div className="text-[9px] font-mono text-[#3f3f46] border border-[#27272a] px-2 py-1">
          COSINE SIM · {data.length}×{data.length > 0 ? data[0].data.length : 0}
        </div>
      </div>

      {/* Heatmap */}
      <div className="flex-1 px-4 py-4" style={{ height: 340 }}>
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-[10px] font-mono text-[#3b82f6] animate-pulse tracking-widest">
              COMPUTING SIMILARITY VECTORS...
            </div>
          </div>
        ) : (
          <ResponsiveHeatMap
            data={data}
            margin={{ top: 40, right: 60, bottom: 20, left: 90 }}
            valueFormat=">-.2f"
            axisTop={{
              tickSize: 0,
              tickPadding: 8,
              legend: "",
              tickRotation: -30,
              legendOffset: 36,
              renderTick: ({ x, y, value }) => (
                <text
                  x={x}
                  y={y - 8}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  style={{
                    fontSize: 9,
                    fontFamily: "monospace",
                    fill: "#71717a",
                    transform: `rotate(-30deg)`,
                  }}
                >
                  {value}
                </text>
              ),
            }}
            axisLeft={{
              tickSize: 0,
              tickPadding: 10,
              renderTick: ({ x, y, value }) => (
                <text
                  x={x - 8}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  style={{ fontSize: 9, fontFamily: "monospace", fill: "#71717a" }}
                >
                  {value}
                </text>
              ),
            }}
            colors={{
              type: "sequential",
              scheme: "blues",
              minValue: 0,
              maxValue: 1,
            }}
            emptyColor="#111113"
            borderWidth={1}
            borderColor="#0c0c0e"
            enableLabels={true}
            labelTextColor={{ from: "color", modifiers: [["brighter", 3]] }}
            tooltip={({ cell }) => (
              <div className="bg-[#0f0f0f] border border-[#1d4ed8]/40 px-3 py-2 text-xs font-mono shadow-xl">
                <p className="text-[#60a5fa] mb-1">SIMILARITY INDEX</p>
                <p className="text-[#a1a1aa]">
                  {cell.serieId} ↔ {cell.data.x}
                </p>
                <p className="text-white font-bold mt-1">
                  {typeof cell.value === "number" ? cell.value.toFixed(3) : cell.value}
                </p>
              </div>
            )}
            theme={{
              text: { fill: "#71717a", fontFamily: "monospace", fontSize: 9 },
              tooltip: { container: { background: "transparent", boxShadow: "none", padding: 0 } },
            }}
          />
        )}
      </div>

      {/* Scale legend */}
      <div className="border-t border-[#1f1f23] px-4 py-2 flex items-center gap-3">
        <span className="text-[9px] font-mono text-[#3f3f46]">LOW</span>
        <div className="flex-1 h-1.5 rounded-full bg-gradient-to-r from-[#0c0c0e] via-[#1d4ed8] to-[#93c5fd]" />
        <span className="text-[9px] font-mono text-[#3f3f46]">HIGH</span>
        <span className="text-[9px] font-mono text-[#27272a] ml-4">
          PEARSON COSINE ∈ [0,1]
        </span>
      </div>
    </div>
  );
}
