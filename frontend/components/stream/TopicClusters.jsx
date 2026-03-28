"use client";
import {
  ResponsiveContainer, BarChart, Bar,
  XAxis, YAxis, Cell, Tooltip,
} from "recharts";

const GOLD = "#FFB800";
const GOLD_DIM = "#8B7500";

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2 border-l-2"
      style={{ background: "rgba(10,8,6,0.95)", borderColor: GOLD, border: `1px solid rgba(255,184,0,0.25)` }}
    >
      <p className="text-[10px] font-mono text-white/50 uppercase tracking-widest mb-1">
        {payload[0].payload.fullLabel}
      </p>
      <p className="text-base font-mono font-bold" style={{ color: GOLD }}>
        {payload[0].value.toFixed(1)}%
      </p>
    </div>
  );
};

export default function TopicClusters({ topics }) {
  if (!topics?.length) {
    return (
      <p className="text-xs font-mono text-white/25 py-4 px-2">
        No topic clusters extracted.
      </p>
    );
  }

  const data = topics.slice(0, 8).map((t, i) => ({
    label: (Array.isArray(t.keywords) ? t.keywords.slice(0, 2).join(", ") : `Topic ${t.topic_id}`),
    fullLabel: Array.isArray(t.keywords) ? t.keywords.slice(0, 4).join(", ") : `Topic ${t.topic_id}`,
    value: parseFloat(t.size_percent) || 0,
    id: t.topic_id ?? i,
  }));

  return (
    <div className="h-full flex flex-col gap-2 px-1">
      {/* Treemap-style pills (top 3 dominant) */}
      <div className="flex flex-wrap gap-1.5 mb-1">
        {data.slice(0, 4).map((d) => (
          <span
            key={d.id}
            className="px-2.5 py-1 text-[9px] font-mono font-bold uppercase tracking-wider"
            style={{
              background: "rgba(255,184,0,0.08)",
              border: "1px solid rgba(255,184,0,0.22)",
              color: GOLD,
            }}
          >
            {d.label}
            <span className="ml-1.5 text-white/30">{d.value.toFixed(0)}%</span>
          </span>
        ))}
      </div>

      {/* Bar chart */}
      <div className="flex-1 min-h-0" style={{ minHeight: "100px" }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ top: 0, right: 32, bottom: 0, left: 8 }}
            barCategoryGap="18%"
          >
            <XAxis
              type="number"
              domain={[0, 100]}
              tick={{ fill: "rgba(255,255,255,0.2)", fontSize: 9, fontFamily: "monospace" }}
              axisLine={{ stroke: "rgba(255,255,255,0.06)" }}
              tickLine={false}
              tickFormatter={v => `${v}%`}
            />
            <YAxis
              dataKey="label"
              type="category"
              width={90}
              tick={{ fill: "rgba(255,255,255,0.45)", fontSize: 9, fontFamily: "monospace" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,184,0,0.04)" }} />
            <Bar dataKey="value" radius={[0, 2, 2, 0]}>
              {data.map((entry, i) => (
                <Cell
                  key={entry.id}
                  fill={i === 0 ? GOLD : i === 1 ? "#CC9400" : GOLD_DIM}
                  fillOpacity={1 - i * 0.06}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
