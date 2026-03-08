"use client";
import { useEffect, useState } from "react";
import EchoScoreBar from "@/components/polar/EchoScoreBar";
import SimilarityHeatmap from "@/components/polar/SimilarityHeatmap";
import PolarizeTreemap from "@/components/polar/PolarizeTreemap";
import IntelligenceBrief from "@/components/polar/IntelligenceBrief";

const NAV_ITEMS = ["INGESTS", "THEATER", "OPERATIONS", "POLARIZE"];

function StatusDot({ color, label }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={`w-1.5 h-1.5 rounded-full ${color} animate-pulse`} />
      <span className="text-[8px] font-mono text-[#52525b] tracking-widest">{label}</span>
    </div>
  );
}

export default function PolarizePage() {
  const [timestamp, setTimestamp] = useState("");

  useEffect(() => {
    const update = () =>
      setTimestamp(
        new Date().toISOString().replace("T", " ").split(".")[0] + " UTC"
      );
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div
      className="min-h-screen bg-black text-white flex flex-col"
      style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Courier New', monospace" }}
    >
      {/* Top navigation bar */}
      <header className="border-b border-[#1a1a1a] bg-[#080809] flex items-center justify-between px-5 py-2.5 sticky top-0 z-40">
        <div className="flex items-center gap-4">
          <div>
            <p className="text-[8px] font-mono text-[#3b82f6] tracking-[0.3em] uppercase leading-none">
              NarrativeSignal
            </p>
            <p className="text-[10px] font-mono text-white tracking-[0.15em] uppercase font-bold">
              Intelligence Platform
            </p>
          </div>
          <div className="w-px h-6 bg-[#1f1f23]" />
          <nav className="flex gap-1">
            {NAV_ITEMS.map((item) => (
              <button
                key={item}
                className={`text-[9px] font-mono px-3 py-1.5 tracking-widest uppercase transition-all ${
                  item === "POLARIZE"
                    ? "text-[#3b82f6] bg-[#3b82f6]/10 border-b border-[#3b82f6]"
                    : "text-[#3f3f46] hover:text-[#71717a]"
                }`}
              >
                {item}
              </button>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          <StatusDot color="bg-[#3b82f6]" label="STREAM ACTIVE" />
          <StatusDot color="bg-emerald-500" label="API NOMINAL" />
          <div className="text-[8px] font-mono text-[#27272a] border border-[#1a1a1a] px-2 py-1">
            {timestamp}
          </div>
          <div className="w-6 h-6 border border-[#27272a] flex items-center justify-center text-[#52525b] text-[10px]">
            ✕
          </div>
        </div>
      </header>

      {/* Page title bar */}
      <div className="border-b border-[#111113] px-5 py-3 flex items-center justify-between bg-[#08080a]">
        <div className="flex items-center gap-3">
          <div className="w-1 h-5 bg-[#3b82f6]" />
          <div>
            <h1 className="text-xs font-mono font-bold text-white tracking-[0.2em] uppercase">
              POLARIZE
            </h1>
            <p className="text-[9px] font-mono text-[#3f3f46] mt-0.5">
              Media Ecosystem Polarization & Echo Chamber Analysis
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[9px] font-mono text-[#3f3f46]">
          <span className="border border-[#1f1f23] px-2 py-0.5">WINDOW: T-30D</span>
          <span className="border border-[#1f1f23] px-2 py-0.5">NODES: 6</span>
          <span className="border border-[#1d4ed8]/40 text-[#3b82f6] px-2 py-0.5">LIVE ANALYSIS</span>
        </div>
      </div>

      {/* Main content */}
      <main className="flex-1 p-4 flex flex-col gap-4">

        {/* Row 1: Echo Scores + Treemap */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4" style={{ minHeight: 400 }}>
          <EchoScoreBar />
          <PolarizeTreemap />
        </div>

        {/* Row 2: Similarity Matrix */}
        <SimilarityHeatmap />

        {/* Row 3: Intelligence Brief */}
        <IntelligenceBrief />
      </main>

      {/* Footer */}
      <footer className="border-t border-[#111113] px-5 py-2 flex items-center justify-between bg-[#08080a]">
        <div className="flex items-center gap-4">
          <span className="text-[8px] font-mono text-[#27272a]">
            NARRATIVESIGNAL v2.4.1
          </span>
          <span className="text-[8px] font-mono text-[#27272a]">
            POLARIZE MODULE
          </span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-[8px] font-mono text-[#1f1f23]">
            DATA LATENCY: ~2min
          </span>
          <span className="text-[8px] font-mono text-[#1f1f23]">
            MODEL: NS-ECHO-3
          </span>
        </div>
      </footer>
    </div>
  );
}
