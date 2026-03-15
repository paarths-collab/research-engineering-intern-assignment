"use client";
import { useState, useEffect, useCallback, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import dynamic from "next/dynamic";

// ── Design tokens ─────────────────────────────────────────────────────────────
const BG = "#0a0806"; 
const ACCENT = "#FFB800"; 
const GOLD = "#8B7500";   
const ORANGE = "#FFD54F"; 
const RED = "#FACC15";    
const BORDER = "rgba(255,184,0,0.1)";
const PANEL_BG = "rgba(10,8,6,0.85)"; 

// ── Dynamic import (SSR-safe) ─────────────────────────────────────────────────
const IntelligenceGraph = dynamic(
  () => import("@/components/network/IntelligenceGraph"),
  {
    ssr: false,
    loading: () => (
      <div className="w-full h-full flex items-center justify-center gap-3 bg-[#060a10]">
        <div className="w-5 h-5 border-2 border-t-transparent rounded-full animate-spin"
          style={{ borderColor: `${ACCENT}aa transparent ${ACCENT}aa ${ACCENT}aa` }} />
        <span className="text-[10px] uppercase tracking-widest animate-pulse font-mono" style={{ color: ACCENT }}>
          Initialising Ecosystem Map…
        </span>
      </div>
    ),
  }
);

// ── Components ────────────────────────────────────────────────────────────────
function SectionHeader({ label, badge, accent = ACCENT, actions }) {
  return (
    <div className="flex items-center gap-3 px-4 py-3" style={{ borderBottom: `1px solid ${BORDER}` }}>
      <div className="w-1 h-4 flex-shrink-0" style={{ background: accent, boxShadow: `0 0 8px ${accent}50` }} />
      <h2 className="text-[10px] font-black uppercase tracking-[0.2em] font-mono" style={{ color: accent }}>{label}</h2>
      {badge && (
        <span className="ml-auto text-[9px] font-mono px-1.5 py-0.5"
          style={{ background: `${accent}15`, color: accent, border: `1px solid ${accent}30` }}>{badge}</span>
      )}
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </div>
  );
}

function NarrativeRow({ narrative, isActive, onClick }) {
    return (
        <button onClick={onClick}
            className="w-full text-left px-4 py-3 transition-all hover:bg-white/5 border-b"
            style={{ 
                borderBottomColor: BORDER,
                background: isActive ? "rgba(255,184,0,0.05)" : "transparent",
                borderLeft: isActive ? `3px solid ${ACCENT}` : "3px solid transparent"
            }}
        >
            <div className="text-[14px] font-mono leading-snug line-clamp-3 mb-1.5 font-bold"
              style={{ color: "#F8FAFC" }}>
                {narrative.representative_title}
            </div>
            <div className="flex items-center gap-3">
                <span className="text-[9px] font-mono font-bold" style={{ color: ACCENT }}>
                    ↑ {narrative.spread_score?.toFixed(2)}
                </span>
                <span className="text-[9px] font-mono opacity-40">
                    {narrative.author_count} authors · {narrative.community_count} subs
                </span>
                {narrative.primary_domain && (
                    <span className="text-[8px] font-mono px-1 py-0.5 ml-auto opacity-30 border border-white/10">
                        {narrative.primary_domain}
                    </span>
                )}
            </div>
            <div className="mt-1 text-[9px] font-mono" style={{ color: "rgba(255,255,255,0.48)" }}>
              Started by {narrative.starter_author ? `u/${narrative.starter_author}` : "unknown"} in {narrative.starter_subreddit ? `r/${narrative.starter_subreddit}` : "unknown"}
              {narrative.start_timestamp ? ` · ${new Date(narrative.start_timestamp).toLocaleString()}` : ""}
            </div>
        </button>
    );
}

export default function IntelligencePage() {
  const [graphData, setGraphData] = useState(null);
  const [focusedGraphData, setFocusedGraphData] = useState(null);
  const [focusedSubreddit, setFocusedSubreddit] = useState(null);
  const [narratives, setNarratives] = useState([]);
  const [leaderboard, setLeaderboard] = useState([]);
  const [spreadLevels, setSpreadLevels] = useState({});
  const [subredditReach, setSubredditReach] = useState({});
  
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState("spread"); // spread | sources | amplifiers

  const [minAuthors, setMinAuthors] = useState(1);
  const [minSubreddits, setMinSubreddits] = useState(0);
  
  const [selectedNarrativeId, setSelectedNarrativeId] = useState(null);
  const [overlayEdges, setOverlayEdges] = useState([]);
  const [selectedNode, setSelectedNode] = useState(null);
  const [subredditInsight, setSubredditInsight] = useState(null);
  const [subredditInsightLoading, setSubredditInsightLoading] = useState(false);
  const [analysisReport, setAnalysisReport] = useState("");
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [isAiPanelMaximized, setIsAiPanelMaximized] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState({
    filters: false,
    amplifiers: false,
    headlines: false,
    narratives: false,
    nodeInfo: false,
  });

  // ── Bootstrap metadata (spread/reach/timeline) ───────────────────────────
  useEffect(() => {
    async function loadMeta() {
      try {
        const [spreadRes, reachRes] = await Promise.all([
          fetch("/api/network/intelligence/spread-levels"),
          fetch("/api/network/intelligence/subreddit-reach"),
        ]);

        if (spreadRes.ok) setSpreadLevels(await spreadRes.json());
        if (reachRes.ok) setSubredditReach(await reachRes.json());
      } catch (e) {
        console.error(e);
      }
    }
    loadMeta();
  }, []);

  // ── 1. Fetch Graphs (Tri-mode) ──────────────────────────────────────────────
  useEffect(() => {
    async function fetchGraph() {
      setLoading(true);
      setFocusedGraphData(null);
      setFocusedSubreddit(null);
      try {
        const q = new URLSearchParams({
          mode: viewMode,
          min_authors: String(minAuthors),
          min_subreddits: String(minSubreddits),
        });

        const res = await fetch(`/api/network/intelligence/graph?${q.toString()}`);
        if (res.ok) setGraphData(await res.json());
      } catch (e) { console.error(e); }
      finally { setLoading(false); }
    }
    fetchGraph();
  }, [viewMode, minAuthors, minSubreddits]);

  // ── 2. Fetch Narratives List ──────────────────────────────────────────────
  useEffect(() => {
    async function fetchNarratives() {
      try {
        const q = new URLSearchParams({
          min_authors: String(minAuthors),
          min_subreddits: String(minSubreddits),
          limit: "300",
        });

        const res = await fetch(`/api/network/intelligence/narratives?${q.toString()}`);
        if (res.ok) {
          const data = await res.json();
          setNarratives(data.items || []);
        }
      } catch (e) { console.error(e); }
    }
    fetchNarratives();
  }, [minAuthors, minSubreddits]);

  // ── 3. Fetch Leaderboard ────────────────────────────────────────────────
  useEffect(() => {
    async function fetchLeaderboard() {
      try {
        const q = new URLSearchParams({ limit: "30" });

        const res = await fetch(`/api/network/intelligence/leaderboard?${q.toString()}`);
        if (res.ok) {
          const data = await res.json();
          setLeaderboard(data.items || []);
        }
      } catch (e) {
        console.error(e);
      }
    }
    fetchLeaderboard();
  }, []);

  // ── 4. Handle Narrative Selection (Overlay) ────────────────────────────────
  const handleSelectNarrative = useCallback(async (narrativeId) => {
    if (selectedNarrativeId === narrativeId) {
        setSelectedNarrativeId(null);
        setOverlayEdges([]);
        return;
    }
    setSelectedNarrativeId(narrativeId);
    setAnalysisReport("");
    try {
        const res = await fetch(`/api/network/intelligence/narrative/${narrativeId}/overlay`);
        if (res.ok) {
            const data = await res.json();
            setOverlayEdges(data.edges || []);
        }
    } catch (e) { console.error(e); }
  }, [selectedNarrativeId]);

  const runNarrativeAnalysis = useCallback(async () => {
    if (!selectedNarrativeId) return;
    setAnalysisLoading(true);
    try {
      const res = await fetch(`/api/network/intelligence/narrative/${selectedNarrativeId}/analyze`, { method: "POST" });
      const payload = await res.json();
      if (res.ok) {
        setAnalysisReport(payload.report || "No analysis returned.");
      } else {
        setAnalysisReport(payload?.detail || "Analysis failed.");
      }
    } catch (e) {
      setAnalysisReport("Analysis failed.");
      console.error(e);
    } finally {
      setAnalysisLoading(false);
    }
  }, [selectedNarrativeId]);

  const handleNodeClick = useCallback(async (node) => {
    setSelectedNode(node);
    setSubredditInsight(null);

    if (!node || node.type !== "subreddit" || !node.label) {
      return;
    }

    setSubredditInsightLoading(true);
    try {
      setSelectedNarrativeId(null);
      setOverlayEdges([]);

      const q = new URLSearchParams({
        min_authors: String(minAuthors),
        min_subreddits: String(minSubreddits),
      });
      const [detailRes, ecoRes] = await Promise.all([
        fetch(
        `/api/network/intelligence/subreddit/${encodeURIComponent(node.label)}/details?${q.toString()}`
        ),
        fetch(`/api/network/intelligence/subreddit/${encodeURIComponent(node.label)}/ecosystem?${q.toString()}`),
      ]);

      if (detailRes.ok) {
        setSubredditInsight(await detailRes.json());
      }

      if (ecoRes && ecoRes.ok) {
        const eco = await ecoRes.json();
        setFocusedGraphData({ nodes: eco.nodes || [], edges: eco.edges || [] });
        setFocusedSubreddit(node.label);
      } else {
        setFocusedGraphData(null);
        setFocusedSubreddit(null);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSubredditInsightLoading(false);
    }
  }, [minAuthors, minSubreddits]);

  const handleResetSubredditFocus = useCallback(() => {
    setFocusedGraphData(null);
    setFocusedSubreddit(null);
  }, []);

  useEffect(() => {
    if (!String(analysisReport || "").trim()) {
      setIsAiPanelMaximized(false);
    }
  }, [analysisReport]);

  const toggleSection = useCallback((sectionKey) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [sectionKey]: !prev[sectionKey],
    }));
  }, []);

  const displayedGraphData = focusedGraphData || graphData;

  const spreadFilterButtons = useMemo(() => {
    const levels = Object.keys(spreadLevels || {})
      .map((k) => Number.parseInt(String(k).replace("+", ""), 10))
      .filter((n) => Number.isFinite(n));
    const merged = Array.from(new Set([1, ...levels, minAuthors]));
    return merged.sort((a, b) => a - b);
  }, [spreadLevels, minAuthors]);

  const reachFilterButtons = useMemo(() => {
    const levels = Object.keys(subredditReach || {})
      .map((k) => Number.parseInt(String(k).replace("+", ""), 10))
      .filter((n) => Number.isFinite(n));
    const merged = Array.from(new Set([1, ...levels, minSubreddits || 1]));
    return merged.sort((a, b) => a - b);
  }, [subredditReach, minSubreddits]);

  const visibleHeadlines = useMemo(() => {
    return (narratives || [])
      .filter((n) => (n?.representative_title || "").trim().length > 0)
      .slice(0, 8)
      .map((n) => ({
        id: n.narrative_id,
        title: n.representative_title,
      }));
  }, [narratives]);

  const narrativeFlowSteps = useMemo(() => {
    if (!selectedNarrativeId || !Array.isArray(overlayEdges) || overlayEdges.length === 0) return [];

    const nodeMap = new Map();
    for (const n of graphData?.nodes || []) {
      nodeMap.set(n.id, n.label || n.id);
    }
    for (const n of focusedGraphData?.nodes || []) {
      nodeMap.set(n.id, n.label || n.id);
    }

    const prettifyNodeId = (rawId) => {
      const value = String(rawId || "").trim();
      if (!value) return "unknown";
      if (value.startsWith("sub::")) return `r/${value.slice(5)}`;
      if (value.startsWith("author::")) return `u/${value.slice(8)}`;
      return value;
    };

    return overlayEdges.slice(0, 25).map((edge, idx) => {
      const fromId = edge.from ?? edge.source;
      const toId = edge.to ?? edge.target;
      const fromLabel = nodeMap.get(fromId) || prettifyNodeId(fromId);
      const toLabel = nodeMap.get(toId) || prettifyNodeId(toId);
      return {
        id: `${fromId || "unknown"}-${toId || "unknown"}-${idx}`,
        from: fromLabel,
        to: toLabel,
        relation: edge.relation || "flows_to",
      };
    });
  }, [selectedNarrativeId, overlayEdges, graphData, focusedGraphData]);

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col font-mono" style={{ background: BG, color: "#e2e8f0" }}>
      
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="flex-shrink-0 px-8 py-5 flex items-center justify-between"
        style={{ borderBottom: `1px solid ${BORDER}`, background: "rgba(0,0,0,0.4)" }}>
        <div className="flex items-center gap-5">
          <div className="h-10 w-1" style={{ background: ACCENT }} />
          <div>
            <div className="text-[9px] uppercase font-bold tracking-[0.4em]" style={{ color: `${ACCENT}55` }}>
              NarrativeSignal · Narrative Ecosystem · SNTIS
            </div>
            <h1 className="text-2xl font-black uppercase tracking-tighter leading-none text-white">Ecosystem Explorer</h1>
          </div>
        </div>

        {/* View Mode Switcher */}
        <div className="flex items-center gap-1.5 p-1 bg-white/5 rounded-sm border border-white/10">
            {[
              { id: "spread", label: "Spread", color: "#FFB800" },
              { id: "sources", label: "Sources", color: "#FFD54F" },
              { id: "amplifiers", label: "Amplifiers", color: "#FFE08A" }
            ].map(m => (
                <button key={m.id} onClick={() => setViewMode(m.id)}
                    className={`text-[10px] uppercase font-bold tracking-wider px-3 py-1.5 transition-all ${viewMode === m.id ? 'opacity-100' : 'opacity-30 hover:opacity-100'}`}
                    style={{
                        background: viewMode === m.id ? `${m.color}20` : "transparent",
                        color: m.color,
                        border: `1px solid ${viewMode === m.id ? `${m.color}40` : 'transparent'}`
                    }}
                >
                    {m.label}
                </button>
            ))}
        </div>
      </header>

      {/* ── Main Layout ────────────────────────────────────────────────── */}
      <main className="flex-1 flex overflow-hidden">
        
        {/* Left: Ecosystem Graph */}
        <section className="flex-1 relative flex flex-col min-w-0" style={{ borderRight: `1px solid ${BORDER}` }}>
            <SectionHeader
              label="Narrative Ecosystem"
              badge={`${viewMode.toUpperCase()} · authors>=${minAuthors} · subs>=${minSubreddits}${focusedSubreddit ? ` · focus=r/${focusedSubreddit}` : ""}`}
              actions={focusedSubreddit ? (
                <button
                  onClick={handleResetSubredditFocus}
                  className="text-[9px] uppercase tracking-wider px-2 py-1 border"
                  style={{ borderColor: "rgba(250,204,21,0.45)", color: "#FACC15", background: "rgba(250,204,21,0.1)" }}
                >
                  Clear Focus
                </button>
              ) : null}
            />

            <div className="flex-1 relative">
                {loading && (
                    <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/40 backdrop-blur-sm">
                        <div className="flex flex-col items-center gap-3">
                            <div className="w-6 h-6 border-2 border-t-transparent border-white/20 rounded-full animate-spin" 
                                style={{ borderTopColor: ACCENT }} />
                            <span className="text-[9px] uppercase tracking-[0.2em] text-white/40">Syncing Graph Data…</span>
                        </div>
                    </div>
                )}
                <IntelligenceGraph 
                    graphData={displayedGraphData} 
                  onNodeClick={handleNodeClick} 
                    selectedNodeId={selectedNode?.id}
                    overlayEdges={overlayEdges}
                />
            </div>
            
            {/* Legend / Overlay Hint */}
            {selectedNarrativeId && (
                <div className="absolute bottom-5 left-5 z-20 px-4 py-3 bg-black/80 backdrop-blur-md border border-amber-500/40">
                  <div className="text-[9px] uppercase tracking-widest text-amber-300 font-bold mb-1">Active Overlay</div>
                    <div className="text-[11px] font-bold text-white max-w-xs line-clamp-1">
                      {narratives.find(n => n.narrative_id === selectedNarrativeId)?.representative_title || "Narrative Path"}
                    </div>
                    {(() => {
                      const n = narratives.find((x) => x.narrative_id === selectedNarrativeId);
                      if (!n) return null;
                      return (
                        <div className="mt-1 text-[9px]" style={{ color: "rgba(255,255,255,0.62)" }}>
                          Started by {n.starter_author ? `u/${n.starter_author}` : "unknown"} in {n.starter_subreddit ? `r/${n.starter_subreddit}` : "unknown"}
                          {n.start_timestamp ? ` · ${new Date(n.start_timestamp).toLocaleString()}` : ""}
                        </div>
                      );
                    })()}
                    <div className="flex items-center gap-2 mt-2">
                      <span className="w-8 h-0.5 bg-amber-400 shadow-[0_0_8px_#fbbf24]" />
                        <span className="text-[9px] text-white/40 uppercase">Spread sequence</span>
                    </div>
                </div>
            )}
        </section>

          {/* Right: Narrative Explorer */}
            <aside className="sidebar-container relative w-[520px] max-w-[48vw] min-w-[420px] h-full min-h-0 flex flex-col flex-shrink-0 overflow-hidden" style={{ background: PANEL_BG }}>
            <div className="sidebar-header flex-shrink-0">
              <SectionHeader
                label="Narrative Explorer"
                badge="INVESTIGATE"
                actions={(
                  <button
                    onClick={() => setIsAiPanelMaximized(true)}
                    disabled={!String(analysisReport || "").trim()}
                    className="text-[9px] uppercase tracking-[0.16em] px-2 py-1 border"
                    style={{
                      borderColor: "rgba(250,204,21,0.45)",
                      color: "#FACC15",
                      background: "rgba(250,204,21,0.1)",
                      opacity: String(analysisReport || "").trim() ? 1 : 0.45,
                    }}
                    title="Maximize AI analysis"
                  >
                    Maximize AI
                  </button>
                )}
              />
            </div>

            <div className="px-4 py-3 border-b" style={{ borderColor: BORDER }}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[9px] uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.4)" }}>
                  Narrative Spread
                </div>
                <button
                  onClick={() => toggleSection("filters")}
                  className="text-[9px] uppercase tracking-[0.16em] px-2 py-0.5 border"
                  style={{ borderColor: "rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.62)" }}
                >
                  {collapsedSections.filters ? "Expand" : "Collapse"}
                </button>
              </div>

              {!collapsedSections.filters && (
                <>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                {spreadFilterButtons.map((v) => (
                  <button
                    key={`auth-${v}`}
                    onClick={() => setMinAuthors(v)}
                    className="text-[9px] px-2 py-1 border font-mono"
                    style={{
                      borderColor: minAuthors === v ? `${ACCENT}55` : "rgba(255,255,255,0.1)",
                      color: minAuthors === v ? ACCENT : "rgba(255,255,255,0.6)",
                      background: minAuthors === v ? `${ACCENT}12` : "transparent",
                    }}
                  >
                    {v}+ Authors ({spreadLevels?.[`${v}+`] ?? 0})
                  </button>
                ))}
                  </div>

                  <div className="text-[9px] uppercase tracking-[0.2em] mb-2" style={{ color: "rgba(255,255,255,0.4)" }}>
                    Subreddit Reach
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                <button
                  onClick={() => setMinSubreddits(0)}
                  className="text-[9px] px-2 py-1 border font-mono"
                  style={{
                    borderColor: minSubreddits === 0 ? `${ACCENT}55` : "rgba(255,255,255,0.1)",
                    color: minSubreddits === 0 ? ACCENT : "rgba(255,255,255,0.6)",
                    background: minSubreddits === 0 ? `${ACCENT}12` : "transparent",
                  }}
                >
                  Any
                </button>
                {reachFilterButtons.map((v) => (
                  <button
                    key={`sub-${v}`}
                    onClick={() => setMinSubreddits(v)}
                    className="text-[9px] px-2 py-1 border font-mono"
                    style={{
                      borderColor: minSubreddits === v ? `${ACCENT}55` : "rgba(255,255,255,0.1)",
                      color: minSubreddits === v ? ACCENT : "rgba(255,255,255,0.6)",
                      background: minSubreddits === v ? `${ACCENT}12` : "transparent",
                    }}
                  >
                    {v}+ Subreddits ({subredditReach?.[`${v}+`] ?? 0})
                  </button>
                ))}
                  </div>
                </>
              )}
            </div>

            <div className="px-4 py-3 border-b" style={{ borderColor: BORDER }}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[9px] uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.4)" }}>
                  Top Amplifiers
                </div>
                <button
                  onClick={() => toggleSection("amplifiers")}
                  className="text-[9px] uppercase tracking-[0.16em] px-2 py-0.5 border"
                  style={{ borderColor: "rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.62)" }}
                >
                  {collapsedSections.amplifiers ? "Expand" : "Collapse"}
                </button>
              </div>

              {!collapsedSections.amplifiers && (
                <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1" style={{ scrollbarWidth: "thin" }}>
                {leaderboard.slice(0, 10).map((u, idx) => (
                  <div key={`${u.author}-${idx}`} className="flex items-center justify-between text-[10px] font-mono">
                    <span className="truncate" style={{ color: "rgba(255,255,255,0.74)", maxWidth: 180 }}>
                      {idx + 1}. u/{u.author}
                    </span>
                    <span style={{ color: ACCENT }}>{u.post_count}</span>
                  </div>
                ))}
                {leaderboard.length === 0 && (
                  <div className="text-[10px] font-mono" style={{ color: "rgba(255,255,255,0.3)" }}>
                    No leaderboard data for selected timeline.
                  </div>
                )}
                </div>
              )}
            </div>

            <div className="px-4 py-3 border-b" style={{ borderColor: BORDER }}>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[10px] uppercase tracking-[0.2em] font-bold" style={{ color: "#FACC15" }}>
                  Headlines
                </div>
                <button
                  onClick={() => toggleSection("headlines")}
                  className="text-[9px] uppercase tracking-[0.16em] px-2 py-0.5 border"
                  style={{ borderColor: "rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.62)" }}
                >
                  {collapsedSections.headlines ? "Expand" : "Collapse"}
                </button>
              </div>

              {!collapsedSections.headlines && (
                <>
                  <div className="space-y-2 max-h-44 overflow-y-auto pr-1" style={{ scrollbarWidth: "thin" }}>
                {visibleHeadlines.map((h) => (
                  <button
                    key={h.id}
                    onClick={() => handleSelectNarrative(h.id)}
                    className="w-full text-left text-[12px] leading-snug font-bold hover:opacity-100 opacity-90 px-2.5 py-2 border transition-colors"
                    style={{
                      color: "#F8FAFC",
                      borderColor: selectedNarrativeId === h.id ? "rgba(250,204,21,0.55)" : "rgba(255,255,255,0.14)",
                      background: selectedNarrativeId === h.id ? "rgba(250,204,21,0.10)" : "rgba(255,255,255,0.02)",
                    }}
                    title={h.title}
                  >
                    {h.title}
                  </button>
                ))}
                {visibleHeadlines.length === 0 && (
                  <div className="text-[11px]" style={{ color: "rgba(255,255,255,0.55)" }}>
                    No headlines available.
                  </div>
                )}
                  </div>

                  {selectedNarrativeId && (
                <div className="mt-3 border p-2.5" style={{ borderColor: "rgba(255,255,255,0.12)", background: "rgba(255,255,255,0.02)" }}>
                  <div className="text-[9px] uppercase tracking-[0.2em] mb-2" style={{ color: "#FACC15" }}>
                    Narrative Route (From → To)
                  </div>

                  {narrativeFlowSteps.length > 0 ? (
                    <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1" style={{ scrollbarWidth: "thin" }}>
                      {narrativeFlowSteps.map((step, idx) => (
                        <div
                          key={step.id}
                          className="text-[10px] font-mono px-2 py-1.5 border"
                          style={{ borderColor: "rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.82)", background: "rgba(0,0,0,0.2)" }}
                        >
                          <span style={{ color: "rgba(255,255,255,0.55)" }}>{idx + 1}. </span>
                          <span>{step.from}</span>
                          <span style={{ color: "#FACC15" }}> → </span>
                          <span>{step.to}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-[10px]" style={{ color: "rgba(255,255,255,0.55)" }}>
                      Click a headline and wait for overlay to load to see where the narrative moved.
                    </div>
                  )}
                </div>
                  )}
                </>
              )}
            </div>

            {/* List */}
            <div className="narrative-list flex-1 min-h-0 overflow-y-auto" style={{ scrollbarWidth: "thin", paddingRight: "6px" }}>
                <div className="px-4 py-2.5 border-b sticky top-0 z-10" style={{ borderColor: BORDER, background: "rgba(5,7,10,0.95)" }}>
                  <div className="flex items-center justify-between">
                    <div className="text-[9px] uppercase tracking-[0.16em]" style={{ color: "rgba(255,255,255,0.55)" }}>
                      Narrative List
                    </div>
                    <button
                      onClick={() => toggleSection("narratives")}
                      className="text-[9px] uppercase tracking-[0.16em] px-2 py-0.5 border"
                      style={{ borderColor: "rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.62)" }}
                    >
                      {collapsedSections.narratives ? "Expand" : "Collapse"}
                    </button>
                  </div>
                </div>

                {!collapsedSections.narratives && (
                <AnimatePresence mode="popLayout">
                    {narratives.map(narr => (
                        <motion.div key={narr.narrative_id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                            <NarrativeRow 
                                narrative={narr} 
                                isActive={selectedNarrativeId === narr.narrative_id}
                                onClick={() => handleSelectNarrative(narr.narrative_id)}
                            />
                        </motion.div>
                    ))}
                    {narratives.length === 0 && (
                        <div className="p-10 text-center opacity-20 text-[11px] uppercase tracking-widest">
                            No narratives matching criteria
                        </div>
                    )}
                </AnimatePresence>
                    )}
            </div>

            {/* Analyze Narrative */}
            <div
              className="sidebar-footer flex-shrink-0 px-4 py-3 border-t"
              style={{ borderColor: BORDER, position: "sticky", bottom: 0, background: "#05070A", zIndex: 20 }}
            >
              <button
                onClick={runNarrativeAnalysis}
                disabled={!selectedNarrativeId || analysisLoading}
                className="analyze-button w-full py-2 text-[10px] uppercase tracking-[0.18em] font-semibold border transition-colors hover:bg-[#FACC15]"
                style={{
                  borderColor: "#EAB308",
                  color: "#0a0806",
                  background: "#EAB308",
                  opacity: !selectedNarrativeId || analysisLoading ? 0.5 : 1,
                  letterSpacing: "1px",
                }}
              >
                {analysisLoading ? "Analyzing Narrative..." : "Analyze Narrative"}
              </button>

              {!!analysisReport && (
                <>
                  <div className="mt-2 flex justify-end">
                    <button
                      onClick={() => setIsAiPanelMaximized(true)}
                      className="text-[9px] uppercase tracking-[0.16em] px-2 py-1 border"
                      style={{ borderColor: "rgba(250,204,21,0.45)", color: "#FACC15", background: "rgba(250,204,21,0.1)" }}
                    >
                      Maximize AI View
                    </button>
                  </div>
                  <pre className="mt-3 whitespace-pre-wrap text-[10px] leading-relaxed max-h-56 overflow-y-auto" style={{ color: "rgba(255,255,255,0.78)" }}>
                    {analysisReport}
                  </pre>
                </>
              )}
            </div>

            {isAiPanelMaximized && (
              <div className="absolute inset-0 z-50 flex flex-col" style={{ background: "#05070A" }}>
                <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: BORDER }}>
                  <div>
                    <div className="text-[9px] uppercase tracking-[0.2em]" style={{ color: "#FACC15" }}>
                      AI Analysis - Maximized
                    </div>
                    <div className="text-[10px]" style={{ color: "rgba(255,255,255,0.58)" }}>
                      Full narrative intelligence output
                    </div>
                  </div>
                  <button
                    onClick={() => setIsAiPanelMaximized(false)}
                    className="text-[9px] uppercase tracking-[0.16em] px-2 py-1 border"
                    style={{ borderColor: "rgba(255,255,255,0.2)", color: "rgba(255,255,255,0.75)" }}
                  >
                    Close
                  </button>
                </div>

                <div className="flex-1 min-h-0 overflow-y-auto p-4" style={{ scrollbarWidth: "thin" }}>
                  <pre className="whitespace-pre-wrap text-[11px] leading-relaxed" style={{ color: "rgba(255,255,255,0.9)" }}>
                    {analysisReport || "No AI analysis available yet. Click Analyze Narrative first."}
                  </pre>
                </div>
              </div>
            )}

            {/* Node Info (Footer) */}
            <div className="flex-shrink-0 p-4 bg-black/40 border-t" style={{ borderColor: BORDER }}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[9px] uppercase tracking-[0.16em]" style={{ color: "rgba(255,255,255,0.55)" }}>
                    Node Inspector
                  </div>
                  <button
                    onClick={() => toggleSection("nodeInfo")}
                    className="text-[9px] uppercase tracking-[0.16em] px-2 py-0.5 border"
                    style={{ borderColor: "rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.62)" }}
                  >
                    {collapsedSections.nodeInfo ? "Expand" : "Collapse"}
                  </button>
                </div>

                {collapsedSections.nodeInfo ? null : (selectedNode ? (
                    <div>
                        <div className="text-[9px] uppercase tracking-widest text-[#FFB800] mb-1">Selected: {selectedNode.type}</div>
                        <div className="text-[14px] font-bold text-white break-words">{selectedNode.label}</div>
                        {selectedNode.id && (
                          <div className="text-[10px] text-white/45 mt-0.5 font-mono break-all">{selectedNode.id}</div>
                        )}

                        {subredditInsightLoading && selectedNode.type === "subreddit" && (
                          <div className="mt-2 text-[10px] text-amber-300/80 uppercase tracking-wider">Loading subreddit intelligence...</div>
                        )}

                        {!subredditInsightLoading && subredditInsight && selectedNode.type === "subreddit" && (
                          <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] font-mono">
                            <div className="text-white/55">Posts</div><div className="text-amber-300 text-right">{subredditInsight.summary?.total_posts ?? 0}</div>
                            <div className="text-white/55">Authors</div><div className="text-amber-300 text-right">{subredditInsight.summary?.distinct_authors ?? 0}</div>
                            <div className="text-white/55">Domains</div><div className="text-amber-300 text-right">{subredditInsight.summary?.distinct_domains ?? 0}</div>
                            <div className="text-white/55">Narratives</div><div className="text-amber-300 text-right">{subredditInsight.summary?.narratives ?? 0}</div>

                            {subredditInsight.top_domains?.length > 0 && (
                              <>
                                <div className="col-span-2 mt-2 text-white/65 uppercase tracking-wider">Top Sources</div>
                                <div className="col-span-2 text-white/80 leading-snug">
                                  {subredditInsight.top_domains.slice(0, 5).map((d) => d.domain).join(" · ")}
                                </div>
                              </>
                            )}

                            {subredditInsight.top_authors?.length > 0 && (
                              <>
                                <div className="col-span-2 mt-2 text-white/65 uppercase tracking-wider">Top Authors</div>
                                <div className="col-span-2 text-white/80 leading-snug">
                                  {subredditInsight.top_authors.slice(0, 5).map((a) => `u/${a.author}`).join(" · ")}
                                </div>
                              </>
                            )}

                            {subredditInsight.connected_subreddits?.length > 0 && (
                              <>
                                <div className="col-span-2 mt-2 text-white/65 uppercase tracking-wider">Connected Subs</div>
                                <div className="col-span-2 text-white/80 leading-snug">
                                  {subredditInsight.connected_subreddits.slice(0, 5).map((s) => `r/${s.subreddit}`).join(" · ")}
                                </div>
                              </>
                            )}

                            {subredditInsight.top_narratives?.length > 0 && (
                              <>
                                <div className="col-span-2 mt-2 text-amber-300 uppercase tracking-wider font-bold">Headlines</div>
                                <div className="col-span-2 space-y-1">
                                  {subredditInsight.top_narratives.slice(0, 4).map((n) => (
                                    <div key={n.narrative_id} className="text-[11px] leading-snug" style={{ color: "#F8FAFC" }}>
                                      {n.title || "Untitled narrative"}
                                    </div>
                                  ))}
                                </div>
                              </>
                            )}
                          </div>
                        )}
                    </div>
                ) : (
                    <div className="text-[10px] text-white/30 uppercase tracking-widest text-center py-2">Select a node to inspect</div>
                ))}
            </div>
        </aside>

      </main>
    </div>
  );
}
