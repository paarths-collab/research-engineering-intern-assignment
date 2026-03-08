"use client";
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from "recharts";

const MOCK_DATA = [
  { subreddit: "r/politics", score: 0.82 },
  { subreddit: "r/worldnews", score: 0.61 },
  { subreddit: "r/geopolitics", score: 0.53 },
  { subreddit: "r/news", score: 0.47 },
  { subreddit: "r/conspiracy", score: 0.91 },
  { subreddit: "r/europe", score: 0.38 },
];

const CustomTooltip = ({ active, payload }) => {
  if (active && payload?.length) {
    const val = payload[0].value;
    return (
      <div className="bg-[#0f0f0f] border border-[#1d4ed8]/40 px-3 py-2 text-xs font-mono">
        <p className="text-[#60a5fa]">{payload[0].payload.subreddit}</p>
        <p className="text-white">
          ISOLATION SCORE:{" "}
          <span className="text-[#3b82f6]">{val.toFixed(2)}</span>
        </p>
        <p
          className={`mt-1 ${
            val > 0.7
              ? "text-red-400"
              : val > 0.5
              ? "text-amber-400"
              : "text-emerald-400"
          }`}
        >
          {val > 0.7 ? "● HIGH RISK" : val > 0.5 ? "● MODERATE" : "● LOW"}
        </p>
      </div>
    );
  }
  return null;
};

export default function EchoScoreBar() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/echo-scores");
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

  const getBarColor = (score) => {
    if (score > 0.7) return "#ef4444";
    if (score > 0.5) return "#f59e0b";
    return "#3b82f6";
  };

  return (
    <div className="bg-[#0c0c0e] border border-[#1f1f23] rounded-none h-full flex flex-col">
      {/* Header */}
      <div className="border-b border-[#1f1f23] px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-mono text-[#3b82f6] tracking-[0.2em] uppercase">
            Module 01
          </p>
          <h2 className="text-sm font-mono text-white tracking-widest uppercase mt-0.5">
            Echo Isolation Scores
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[#3b82f6] animate-pulse" />
          <span className="text-[10px] font-mono text-[#3b82f6]">LIVE</span>
        </div>
      </div>

      {/* Legend */}
      <div className="px-4 pt-3 flex gap-4">
        {[
          { color: "#ef4444", label: "HIGH" },
          { color: "#f59e0b", label: "MOD" },
          { color: "#3b82f6", label: "LOW" },
        ].map((l) => (
          <div key={l.label} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-sm"
              style={{ background: l.color }}
            />
            <span className="text-[9px] font-mono text-[#52525b]">
              {l.label}
            </span>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="flex-1 px-2 py-3 min-h-0">
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-[10px] font-mono text-[#3b82f6] animate-pulse tracking-widest">
              FETCHING SIGNAL DATA...
            </div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              layout="vertical"
              margin={{ top: 4, right: 20, left: 10, bottom: 4 }}
              barCategoryGap="30%"
            >
              <XAxis
                type="number"
                domain={[0, 1]}
                tick={{ fill: "#52525b", fontSize: 9, fontFamily: "monospace" }}
                axisLine={{ stroke: "#27272a" }}
                tickLine={false}
                tickCount={6}
              />
              <YAxis
                type="category"
                dataKey="subreddit"
                tick={{ fill: "#a1a1aa", fontSize: 9, fontFamily: "monospace" }}
                axisLine={false}
                tickLine={false}
                width={90}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: "#ffffff08" }} />
              <Bar dataKey="score" radius={[0, 2, 2, 0]}>
                {data.map((entry, i) => (
                  <Cell key={i} fill={getBarColor(entry.score)} opacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Footer stat */}
      <div className="border-t border-[#1f1f23] px-4 py-2 flex justify-between">
        <span className="text-[9px] font-mono text-[#3f3f46]">
          SUBREDDITS ANALYZED: {data.length}
        </span>
        <span className="text-[9px] font-mono text-[#3f3f46]">
          AVG:{" "}
          {data.length
            ? (data.reduce((a, b) => a + b.score, 0) / data.length).toFixed(2)
            : "—"}
        </span>
      </div>
    </div>
  );
}
