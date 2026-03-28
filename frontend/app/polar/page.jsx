"use client";
import { useState, useEffect } from "react";
import EchoScoreBar from "@/components/polar/EchoScoreBar";
import SimilarityHeatmap from "@/components/polar/SimilarityHeatmap";
import PolarizeTreemap from "@/components/polar/PolarizeTreemap";
import IntelligenceBrief from "@/components/polar/IntelligenceBrief";

/* ── Design tokens ─────────────────────────────────────── */
const PANEL = {
  background: "rgba(10, 8, 6, 0.4)",
  backdropFilter: "blur(20px)",
  border: "1px solid rgba(255, 184, 0, 0.08)",
  borderRadius: "0px", // Brutalist sharp edges
};

const INNER = {
  background: "rgba(0, 0, 0, 0.2)",
  border: "1px solid rgba(255, 255, 255, 0.03)",
  borderRadius: "0px",
};

/* ── Maximize icon ──────────────────────────────────────── */
function MaximizeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
    </svg>
  );
}

/* ── Reusable panel wrapper ─────────────────────────────── */
function ChartPanel({ title, badge, badgeColor, accentColor, onMaximize, children, className = "", style = {} }) {
  return (
    <div className={`flex flex-col group ${className}`} style={{ ...PANEL, ...style }}>
      <div className="flex items-center gap-3 px-4 pt-4 pb-2 flex-shrink-0">
        <div
          className="w-1.5 h-6 bg-[#FFB800]"
          style={{ boxShadow: `0 0 15px rgba(255, 184, 0, 0.3)` }}
        />
        <h2 className="text-[11px] font-black uppercase tracking-[0.15em] text-white/90 font-manrope">
          {title}
        </h2>
        {badge && (
          <span
            className="ml-auto text-[9px] font-bold px-2 py-0.5 font-mono"
            style={{
              color: "#FFB800",
              background: "rgba(255, 184, 0, 0.1)",
              border: "1px solid rgba(255, 184, 0, 0.2)",
            }}
          >
            {badge}
          </span>
        )}
        <button
          onClick={onMaximize}
          className="ml-2 p-1.5 text-white/20 hover:text-[#FFB800] transition-colors"
        >
          <MaximizeIcon />
        </button>
      </div>
      <div className="flex-1 min-h-0 m-2 overflow-hidden border border-white/5" style={INNER}>
        {children}
      </div>
    </div>
  );
}

/* ── Full-screen modal overlay ──────────────────────────── */
function MaxModal({ title, badge, accentColor, onClose, children }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/90 backdrop-blur-xl" onClick={onClose}>
      <div
        className="w-full max-w-6xl h-full max-h-[92vh] flex flex-col glass-panel shadow-[0_0_100px_rgba(255,184,0,0.1)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-4 px-6 py-5 border-b border-white/5">
          <div className="w-2 h-8 bg-[#FFB800]" />
          <span className="text-xl font-black uppercase tracking-widest text-white font-inter">{title}</span>
          {badge && (
            <span className="text-[10px] font-bold px-3 py-1 bg-[#8B7500]/10 text-[#8B7500] border border-[#8B7500]/20 font-mono">
              {badge}
            </span>
          )}
          <button onClick={onClose} className="ml-auto text-3xl font-mono text-white/20 hover:text-white transition-colors">×</button>
        </div>
        <div className="flex-1 min-h-0 m-6 border border-white/5" style={INNER}>
          {children}
        </div>
      </div>
    </div>
  );
}

/* ── Page ───────────────────────────────────────────────── */
export default function PolarizePage() {
  const [subreddits, setSubreddits] = useState(["politics"]);
  const [selected, setSelected] = useState("politics");
  const [aiOpen, setAiOpen] = useState(false);
  const [maximized, setMaximized] = useState(null);

  useEffect(() => {
    fetch("/api/subreddits")
      .then(res => res.json())
      .then(data => {
        if (data.subreddits) setSubreddits(["all", ...data.subreddits]);
      })
      .catch(err => console.error("Failed to load subreddits", err));
  }, []);

  const PANELS = {
    echo: { title: "Media Diversity Signal", badge: "INTEL_METRIC", accentColor: "#FFB800" },
    heatmap: { title: "Cross-Community Intersection", badge: "OVERLAP_MATRIX", accentColor: "#8B7500" },
    treemap: { title: "Ecosystem Cluster Topology", badge: selected === "all" ? "GLOBAL_ECOSYSTEM" : `R/${selected.toUpperCase()}`, accentColor: "#FFB800" },
  };

  return (
    <div className="h-screen max-h-screen overflow-hidden flex flex-col bg-[#0a0806] font-inter text-[#e6eaf0]">
      {/* ── Header ──────────────────────────────────────────── */}
      <header className="flex-shrink-0 px-8 py-5 flex items-center justify-between border-b border-white/5 bg-black/30">
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-2 bg-gradient-to-r from-[#FFB800] to-[#8B7500] opacity-20 blur-lg animate-pulse" />
            <div className="relative h-10 w-1 bg-white" />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-[10px] uppercase font-bold tracking-[0.4em] text-[#8B7500] font-mono">
                System.Narrative.Polarize
              </span>
              <div className="h-px w-12 bg-white/10" />
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 bg-[#FFB800] animate-ping rounded-full" />
                <span className="text-[10px] uppercase font-bold text-white/40 font-mono">Real-time Stream Active</span>
              </div>
            </div>
            <h1 className="text-3xl font-black uppercase tracking-tighter leading-none text-white">
              Media Ecosystem Intelligence
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setAiOpen(true)}
            className="group relative px-6 py-2.5 bg-transparent border border-[#FFB800]/40 hover:border-[#FFB800] transition-all overflow-hidden"
          >
            <div className="absolute inset-0 bg-[#FFB800] translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
            <div className="relative flex items-center gap-3">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                className="text-[#FFB800] group-hover:text-black transition-colors">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
              <span className="text-xs font-black uppercase tracking-widest text-[#FFB800] group-hover:text-black transition-colors">
                AI Inference
              </span>
            </div>
          </button>
        </div>
      </header>

      {/* ── Main Layout ─────────────────────────────────────── */}
      <main className="flex-1 min-h-0 flex flex-col p-4">
        {/* Subreddit Selector Row */}
        <div className="flex gap-2 mb-4 overflow-x-auto pb-2 shrink-0 scrollbar-hide">
          {subreddits.map(sub => (
            <button
              key={sub}
              onClick={() => setSelected(sub)}
              className={`px-4 py-1.5 font-mono text-xs uppercase tracking-widest border transition-all flex-shrink-0 ${selected === sub
                ? "bg-[#FFB800] text-black border-[#FFB800] font-bold"
                : "bg-transparent text-white/40 border-white/10 hover:border-white/30 hover:text-white"
                }`}
            >
              {sub === "all" ? "Show All Sources" : `r/${sub}`}
            </button>
          ))}
        </div>

        <div className="flex-1 min-h-0 grid grid-cols-12 gap-4">
          {/* Left Col - Signals */}
          <div className="col-span-12 lg:col-span-4 flex flex-col gap-4 min-h-0">
            <ChartPanel
              {...PANELS.echo}
              className="flex-[0.7] min-h-0"
              onMaximize={() => setMaximized("echo")}
            >
              <EchoScoreBar subreddit={selected} onSelect={setSelected} />
            </ChartPanel>

            <ChartPanel
              {...PANELS.heatmap}
              className="flex-[1.5] min-h-0"
              onMaximize={() => setMaximized("heatmap")}
            >
              <SimilarityHeatmap />
            </ChartPanel>
          </div>

          {/* Right Col - Ecosystem */}
          <div className="col-span-12 lg:col-span-8 flex flex-col min-h-0">
            <ChartPanel
              {...PANELS.treemap}
              className="flex-1 min-h-0"
              onMaximize={() => setMaximized("treemap")}
            >
              <PolarizeTreemap subreddit={selected} />
            </ChartPanel>
          </div>
        </div>
      </main>

      {/* ── Modals ─────────────────────────────────────────── */}
      {maximized && (
        <MaxModal
          {...PANELS[maximized]}
          onClose={() => setMaximized(null)}
        >
          {maximized === "echo" && <EchoScoreBar subreddit={selected} onSelect={(s) => { setSelected(s); setMaximized(null); }} isMaximized={true} />}
          {maximized === "heatmap" && <SimilarityHeatmap />}
          {maximized === "treemap" && <PolarizeTreemap subreddit={selected} />}
        </MaxModal>
      )}

      {aiOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center p-8 bg-black/95 backdrop-blur-2xl" onClick={() => setAiOpen(false)}>
          <div className="w-full max-w-3xl glass-panel relative overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="h-1 w-full bg-[#FFB800] shadow-[0_0_20px_#FFB800]" />
            <div className="p-10">
              <div className="flex justify-between items-start mb-10">
                <div>
                  <span className="text-[10px] font-mono text-[#FFB800] uppercase tracking-[0.3em] mb-3 block">Neural Briefing Pattern</span>
                  <h2 className="text-4xl font-black uppercase text-white font-inter tracking-tighter">AI Intelligence Extract</h2>
                </div>
                <button onClick={() => setAiOpen(false)} className="text-4xl font-mono text-white/20 hover:text-white transition-colors">×</button>
              </div>
              <div className="max-h-[60vh] overflow-y-auto pr-4 scrollbar-thin scrollbar-thumb-white/10">
                <IntelligenceBrief subreddit={selected} />
              </div>
              <div className="mt-10 flex justify-end">
                <button
                  onClick={() => setAiOpen(false)}
                  className="px-10 py-3 bg-[#FFB800] text-black font-black uppercase tracking-widest hover:bg-white transition-colors"
                >
                  Terminate Brief
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
