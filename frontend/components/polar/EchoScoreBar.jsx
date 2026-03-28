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
  { subreddit: "r/politics", source_count: 120, score: 0.82 },
  { subreddit: "r/worldnews", source_count: 95, score: 0.61 },
  { subreddit: "r/geopolitics", source_count: 53, score: 0.53 },
  { subreddit: "r/news", source_count: 47, score: 0.47 },
  { subreddit: "r/conspiracy", source_count: 72, score: 0.91 },
  { subreddit: "r/europe", source_count: 38, score: 0.38 },
];

const CustomTooltip = ({ active, payload }) => {
  if (active && payload?.length) {
    return (
      <div className="glass-panel px-4 py-3 border-l-4 border-l-[#FFB800] shadow-2xl">
        <p className="text-white font-bold text-sm tracking-tight mb-1 font-inter uppercase">
          {payload[0].payload.subreddit}
        </p>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-white/50 uppercase tracking-widest">Sources</span>
          <span className="text-[#FFB800] font-mono font-bold text-base">
            {payload[0].payload.source_count ?? "—"}
          </span>
        </div>
      </div>
    );
  }
  return null;
};

export default function EchoScoreBar({ onSelect, subreddit: activeSubreddit, isMaximized = false }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch("/api/echo-scores");
        const json = await res.json();
        const arr = Array.isArray(json) ? json : (json.scores ?? json.data ?? []);
        setData(arr);
      } catch {
        setData(MOCK_DATA);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  const handleBarClick = (entry) => {
    if (onSelect && entry?.subreddit) {
      const sub = entry.subreddit.replace(/^r\//, "");
      onSelect(sub);
    }
  };

  const getBarColor = (isActive) => {
    return isActive ? "#FFB800" : "#8B7500";
  };

  const displayData = isMaximized ? data : data.slice(0, 5);

  return (
    <div className="h-full flex flex-col p-4 bg-[#0a0806]/40">
      {/* Chart */}
      <div className="flex-1 min-h-0">
        {loading ? (
          <div className="h-full flex items-center justify-center">
            <div className="text-[10px] font-mono text-[#FFB800] animate-pulse tracking-[0.3em] uppercase">
              Analyzing Diversity Vectors...
            </div>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={displayData}
              layout="vertical"
              margin={{ top: 10, right: 30, left: 60, bottom: 10 }}
              barCategoryGap="15%"
              onClick={(chartData) => {
                if (chartData?.activePayload?.[0]?.payload) {
                  handleBarClick(chartData.activePayload[0].payload);
                }
              }}
              style={{ cursor: "pointer" }}
            >
              <XAxis
                type="number"
                domain={[0, 1.1]}
                hide
              />
              <YAxis
                type="category"
                dataKey="subreddit"
                interval={0}
                tick={({ x, y, payload }) => {
                  const isActive = payload.value === `r/${activeSubreddit}` || payload.value === activeSubreddit;
                  return (
                    <text
                      x={x - 15}
                      y={y}
                      dy={4}
                      textAnchor="end"
                      fill={isActive ? "#FFB800" : "rgba(255,255,255,0.4)"}
                      fontSize={11}
                      className="font-inter font-semibold uppercase tracking-tight"
                    >
                      {payload.value}
                    </text>
                  );
                }}
                axisLine={false}
                tickLine={false}
                width={180}
              />
              <Tooltip
                content={<CustomTooltip />}
                cursor={{ fill: "rgba(255,184,0,0.05)" }}
                position={{ x: 190 }}
              />
              <Bar dataKey="score" radius={[0, 2, 2, 0]} maxBarSize={60}>
                {data.map((entry, i) => {
                  const isActive = entry.subreddit === `r/${activeSubreddit}` || entry.subreddit === activeSubreddit;
                  return (
                    <Cell
                      key={i}
                      fill={getBarColor(isActive)}
                      fillOpacity={isActive ? 1 : 0.3}
                      stroke={isActive ? "#FFB800" : "none"}
                      strokeWidth={1}
                      className="transition-all duration-300"
                    />
                  );
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
