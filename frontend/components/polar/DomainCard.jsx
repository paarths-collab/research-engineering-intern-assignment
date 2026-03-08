"use client";
import { motion, AnimatePresence } from "framer-motion";

const CATEGORY_COLORS = {
  News: "#3b82f6",
  Advocacy: "#8b5cf6",
  Social: "#f59e0b",
  Blog: "#10b981",
  Government: "#ef4444",
  Academic: "#06b6d4",
};

export default function DomainCard({ domain, onClose }) {
  if (!domain) return null;

  const accentColor = CATEGORY_COLORS[domain.category] || "#3b82f6";
  const liftTier =
    domain.lift > 4 ? "EXTREME" : domain.lift > 2.5 ? "HIGH" : domain.lift > 1.5 ? "MODERATE" : "LOW";
  const liftColor =
    domain.lift > 4
      ? "#ef4444"
      : domain.lift > 2.5
      ? "#f59e0b"
      : domain.lift > 1.5
      ? "#3b82f6"
      : "#10b981";

  return (
    <AnimatePresence>
      <motion.div
        key="domain-card"
        initial={{ x: "100%", opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: "100%", opacity: 0 }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="fixed top-0 right-0 h-full w-80 bg-[#08080a] border-l border-[#1f1f23] z-50 flex flex-col shadow-2xl"
      >
        {/* Top accent bar */}
        <div className="h-0.5 w-full" style={{ background: accentColor }} />

        {/* Header */}
        <div className="px-5 pt-5 pb-4 border-b border-[#1f1f23]">
          <div className="flex items-start justify-between mb-3">
            <p className="text-[9px] font-mono tracking-[0.25em] uppercase" style={{ color: accentColor }}>
              Domain Intelligence
            </p>
            <button
              onClick={onClose}
              className="text-[#52525b] hover:text-white transition-colors text-xs font-mono border border-[#27272a] hover:border-[#52525b] px-2 py-0.5"
            >
              ✕ CLOSE
            </button>
          </div>

          <h3 className="text-lg font-mono text-white tracking-tight break-all leading-tight">
            {domain.name}
          </h3>

          <div
            className="mt-2 inline-flex items-center gap-1.5 px-2 py-0.5 text-[9px] font-mono tracking-widest uppercase"
            style={{ color: accentColor, borderColor: accentColor, border: "1px solid" }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ background: accentColor }}
            />
            {domain.category}
          </div>
        </div>

        {/* Stats */}
        <div className="px-5 py-4 grid grid-cols-2 gap-3 border-b border-[#1f1f23]">
          {[
            { label: "MENTIONS", value: domain.loc, unit: "refs", highlight: false },
            {
              label: "LIFT SCORE",
              value: domain.lift?.toFixed(2),
              unit: "×",
              highlight: true,
              color: liftColor,
            },
          ].map((stat) => (
            <div key={stat.label} className="bg-[#0f0f10] border border-[#1f1f23] p-3">
              <p className="text-[8px] font-mono text-[#52525b] tracking-widest mb-1">
                {stat.label}
              </p>
              <p
                className="text-2xl font-mono font-bold leading-none"
                style={{ color: stat.highlight ? stat.color : "white" }}
              >
                {stat.value}
                <span className="text-xs font-normal text-[#52525b] ml-1">
                  {stat.unit}
                </span>
              </p>
            </div>
          ))}
        </div>

        {/* Lift Tier */}
        <div className="px-5 py-4 border-b border-[#1f1f23]">
          <p className="text-[8px] font-mono text-[#52525b] tracking-widest mb-2">
            LIFT CLASSIFICATION
          </p>
          <div className="flex items-center gap-2">
            <div
              className="flex-1 h-1 rounded-full bg-[#1f1f23] relative overflow-hidden"
            >
              <motion.div
                className="h-full rounded-full"
                style={{ background: liftColor }}
                initial={{ width: 0 }}
                animate={{ width: `${Math.min((domain.lift / 6) * 100, 100)}%` }}
                transition={{ delay: 0.3, duration: 0.8, ease: "easeOut" }}
              />
            </div>
            <span
              className="text-[9px] font-mono font-bold"
              style={{ color: liftColor }}
            >
              {liftTier}
            </span>
          </div>
        </div>

        {/* Signal breakdown */}
        <div className="px-5 py-4 flex-1 border-b border-[#1f1f23]">
          <p className="text-[8px] font-mono text-[#52525b] tracking-widest mb-3">
            SIGNAL METADATA
          </p>
          {[
            { label: "Source Type", value: domain.category },
            { label: "Ecosystem Role", value: domain.lift > 3 ? "Amplifier" : "Contributor" },
            {
              label: "Risk Level",
              value: liftTier,
              color: liftColor,
            },
            { label: "Index", value: `${(domain.loc / 10).toFixed(0)}% share` },
          ].map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between py-1.5 border-b border-[#111113] last:border-0"
            >
              <span className="text-[9px] font-mono text-[#52525b]">{row.label}</span>
              <span
                className="text-[9px] font-mono"
                style={{ color: row.color || "#a1a1aa" }}
              >
                {row.value}
              </span>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="px-5 py-4 flex flex-col gap-2">
          <a
            href={`https://${domain.name}`}
            target="_blank"
            rel="noopener noreferrer"
            className="w-full text-center text-[10px] font-mono tracking-widest py-2.5 transition-colors uppercase"
            style={{
              background: accentColor,
              color: "black",
            }}
          >
            ↗ VISIT DOMAIN
          </a>
          <button
            onClick={onClose}
            className="w-full text-center text-[10px] font-mono tracking-widest py-2.5 border border-[#27272a] text-[#52525b] hover:border-[#52525b] hover:text-white transition-colors uppercase"
          >
            ← BACK TO TREEMAP
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
