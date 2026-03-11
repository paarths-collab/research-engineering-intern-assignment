"use client";
import {
  ResponsiveContainer, LineChart, Line,
  XAxis, YAxis, Tooltip, Legend, ReferenceLine,
} from "recharts";

const COLORS = {
  positive: "#4CAF50",
  neutral: "rgba(255,255,255,0.35)",
  negative: "#EF5350",
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="px-3 py-2"
      style={{ background: "rgba(10,8,6,0.95)", border: "1px solid rgba(255,184,0,0.2)" }}
    >
      <p className="text-[9px] font-mono text-white/40 mb-1.5 uppercase tracking-widest">{label}</p>
      {payload.map(p => (
        <div key={p.dataKey} className="flex items-center gap-2 mb-0.5">
          <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
          <span className="text-[10px] font-mono" style={{ color: p.color }}>
            {p.dataKey.toUpperCase()} {p.value.toFixed(1)}%
          </span>
        </div>
      ))}
    </div>
  );
};

export default function SentimentTrend({ sentiment }) {
  if (!sentiment?.length) {
    return (
      <p className="text-xs font-mono text-white/25 py-4 px-2">
        No sentiment data available.
      </p>
    );
  }

  const data = sentiment.map(s => ({
    date: s.date ? String(s.date).slice(5) : "—",
    positive: parseFloat(s.positive_percent) || 0,
    neutral: parseFloat(s.neutral_percent) || 0,
    negative: parseFloat(s.negative_percent) || 0,
  }));

  return (
    <div className="h-full" style={{ minHeight: "100px" }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart
          data={data}
          margin={{ top: 6, right: 16, bottom: 0, left: 0 }}
        >
          <XAxis
            dataKey="date"
            tick={{ fill: "rgba(255,255,255,0.25)", fontSize: 9, fontFamily: "monospace" }}
            axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={v => `${v}%`}
            domain={[0, 100]}
            tick={{ fill: "rgba(255,255,255,0.2)", fontSize: 9, fontFamily: "monospace" }}
            axisLine={false}
            tickLine={false}
            width={32}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={50} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 4" />
          <Line
            type="monotone"
            dataKey="positive"
            stroke={COLORS.positive}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 4, fill: COLORS.positive }}
          />
          <Line
            type="monotone"
            dataKey="neutral"
            stroke={COLORS.neutral}
            strokeWidth={1}
            strokeDasharray="3 3"
            dot={false}
            activeDot={{ r: 3, fill: COLORS.neutral }}
          />
          <Line
            type="monotone"
            dataKey="negative"
            stroke={COLORS.negative}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 4, fill: COLORS.negative }}
          />
          <Legend
            wrapperStyle={{ fontSize: "9px", fontFamily: "monospace", color: "rgba(255,255,255,0.3)", paddingTop: "4px" }}
            formatter={v => v.toUpperCase()}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
