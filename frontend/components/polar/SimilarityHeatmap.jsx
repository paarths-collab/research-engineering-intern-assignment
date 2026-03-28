"use client";
import { useEffect, useState } from "react";
import { ResponsiveHeatMap } from "@nivo/heatmap";

const SUBS = ["r/politics", "r/Conservative", "r/Liberal", "r/Anarchism", "r/PoliticalDiscussion", "r/Republican", "r/Democrats", "r/neoliberal", "r/socialism", "r/worldpolitics"];

// Generate a symmetric mock 10x10 matrix
const MOCK_DATA = SUBS.map((rowId, i) => ({
  id: rowId,
  data: SUBS.map((colId, j) => ({
    x: colId,
    y: i === j ? Math.floor(15 + Math.random() * 10) : Math.floor(Math.random() * 80),
  })),
}));

export default function SimilarityHeatmap() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/similarity");
        const json = await res.json();
        if (Array.isArray(json) && json.length > 0) {
          setData(json);
        } else if (json.subreddits && json.matrix) {
          const { subreddits, matrix } = json;
          const formatted = subreddits.map((row, i) => ({
            id: row,
            data: subreddits.map((col, j) => ({ x: col, y: matrix[i][j] })),
          }));
          setData(formatted);
        } else {
          setData(MOCK_DATA);
        }
      } catch {
        setData(MOCK_DATA);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  return (
    <div className="h-full flex flex-col p-4 bg-[#0a0806]/40">
      <div className="flex-1 min-h-0">
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-[10px] font-mono text-[#FFB800] animate-pulse tracking-[0.3em] uppercase">
              Mapping Source Overlap...
            </div>
          </div>
        ) : (
          <ResponsiveHeatMap
            data={data}
            margin={{ top: 90, right: 20, bottom: 20, left: 120 }}
            axisTop={{
              tickSize: 0,
              tickPadding: 12,
              tickRotation: -45,
              renderTick: ({ x, y, value }) => (
                <text
                  x={x}
                  y={y - 8}
                  textAnchor="start"
                  className="font-inter font-bold text-[10px] fill-white/40 uppercase tracking-tighter"
                  style={{ transform: `rotate(-45deg)`, transformOrigin: `${x}px ${y}px` }}
                >
                  {value}
                </text>
              ),
            }}
            axisLeft={{
              tickSize: 0,
              tickPadding: 16,
              renderTick: ({ x, y, value }) => (
                <text
                  x={x - 8}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  className="font-inter font-bold text-[10px] fill-white/60 uppercase tracking-tighter"
                >
                  {value}
                </text>
              ),
            }}
            colors={{
              type: "sequential",
              scheme: "oranges", // Using oranges for the golden amber theme
              minValue: 0,
              maxValue: 100,
            }}
            emptyColor="#050508"
            borderWidth={1}
            borderColor="rgba(255,255,255,0.05)"
            enableLabels={true}
            labelTextColor={{ from: "color", modifiers: [["darker", 3]] }}
            tooltip={({ cell }) => (
              <div className="glass-panel px-4 py-3 border-l-4 border-l-[#FFB800] shadow-2xl">
                <span className="text-[9px] font-mono text-[#FFB800] uppercase tracking-[0.2em] mb-1 block">
                  Intersection Signal
                </span>
                <p className="text-white font-bold text-[11px] mb-2 font-inter uppercase">
                  {cell.serieId} <span className="text-white/30">↔</span> {cell.data.x}
                </p>
                <div className="flex items-center gap-2">
                  <span className="text-2xl font-bold font-mono text-white leading-none">
                    {cell.value}
                  </span>
                  <span className="text-[9px] font-mono text-white/50 uppercase tracking-widest">
                    Shared Sources
                  </span>
                </div>
              </div>
            )}
            theme={{
              text: { fill: "rgba(255,255,255,0.4)", fontFamily: "Inter", fontSize: 10 },
              tooltip: { container: { background: "transparent", boxShadow: "none", padding: 0 } },
              grid: { line: { stroke: "rgba(255,255,255,0.03)" } },
              labels: { text: { fill: "#ffffff", fontSize: 12, fontWeight: "bold" } }
            }}
          />
        )}
      </div>
    </div>
  );
}
