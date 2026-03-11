"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import TopicSelector from "./TopicSelector";

const CLUSTER_COLORS = {
  "Geopolitics": "#FFB800",
  "US Politics":  "#FF4081",
  "Economy":      "#00BCD4",
  "Technology":   "#AB47BC",
  "Culture":      "#66BB6A",
};
const GOLD = "#FFB800";

// ── Shared sub-components ────────────────────────────────────

function MetricBadge({ label, value, accent }) {
  return (
    <div
      className="flex flex-col items-center justify-center px-3 py-2"
      style={{ background: "rgba(255,184,0,0.04)", border: "1px solid rgba(255,184,0,0.1)" }}
    >
      <span
        className="text-base font-mono font-black leading-none"
        style={{ color: accent || GOLD }}
      >
        {value ?? "—"}
      </span>
      <span className="text-[8px] font-mono uppercase tracking-widest text-white/30 mt-0.5">
        {label}
      </span>
    </div>
  );
}

function SectionLabel({ children, color }) {
  return (
    <div className="flex items-center gap-2 mb-2">
      <div
        className="w-1 h-5"
        style={{ background: color || GOLD, boxShadow: `0 0 10px ${color || GOLD}55` }}
      />
      <h3 className="text-[9px] font-black uppercase tracking-[0.2em] text-white/70 font-mono">
        {children}
      </h3>
    </div>
  );
}

function Spinner({ color }) {
  return (
    <div
      className="w-4 h-4 rounded-full border-2 border-t-transparent animate-spin"
      style={{ borderColor: `${color || GOLD} transparent ${color || GOLD} ${color || GOLD}` }}
    />
  );
}

function SubredditList({ subreddits }) {
  if (!subreddits?.length) return null;
  return (
    <div className="space-y-1.5">
      {subreddits.map(([name, count]) => (
        <div key={name} className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-white/70">
            r/<span style={{ color: GOLD }}>{name}</span>
          </span>
          <span
            className="text-[9px] font-mono font-bold px-2 py-0.5"
            style={{ background: "rgba(255,184,0,0.08)", border: "1px solid rgba(255,184,0,0.15)", color: GOLD }}
          >
            {count} posts
          </span>
        </div>
      ))}
    </div>
  );
}

function DomainList({ domains }) {
  if (!domains?.length) return null;
  return (
    <div className="space-y-1.5">
      {domains.map(([name, count]) => (
        <div key={name} className="flex items-center justify-between">
          <span className="text-[10px] font-mono text-white/60">{name}</span>
          <span className="text-[9px] font-mono text-white/35">{count} links</span>
        </div>
      ))}
    </div>
  );
}

function HeadlineList({ headlines }) {
  if (!headlines?.length) return null;
  return (
    <ul className="space-y-2">
      {headlines.map((h, i) => (
        <li key={i} className="flex items-start gap-2">
          <span style={{ color: GOLD }} className="text-[10px] font-mono mt-0.5">›</span>
          <span className="text-[10px] font-mono text-white/55 leading-snug">{h}</span>
        </li>
      ))}
    </ul>
  );
}

function BriefRenderer({ brief }) {
  if (!brief) return null;
  return (
    <div className="text-[11px] font-mono leading-relaxed text-white/70">
      <ReactMarkdown
        components={{
          p:      ({ children }) => <p className="mb-3 leading-relaxed">{children}</p>,
          strong: ({ children }) => (
            <strong className="font-black text-[11px]" style={{ color: GOLD }}>{children}</strong>
          ),
          li: ({ children }) => (
            <li className="flex gap-2 mb-1">
              <span style={{ color: GOLD }}>•</span><span>{children}</span>
            </li>
          ),
          ul: ({ children }) => <ul className="space-y-0.5 my-2 pl-1">{children}</ul>,
          h2: ({ children }) => (
            <h2
              className="text-[10px] font-black uppercase tracking-[0.15em] mb-2 mt-4"
              style={{ color: GOLD }}
            >
              {children}
            </h2>
          ),
        }}
      >
        {brief}
      </ReactMarkdown>
    </div>
  );
}

// ── Main panel — 3-stage flow ─────────────────────────────────
// idle → window-loading → topic-select → analyzing → done | failed

export default function SpikeAnalysisPanel({ spike, onClose }) {
  const [stage,   setStage]   = useState("idle");
  const [context, setContext] = useState(null);
  const [topic,   setTopic]   = useState(null);
  const [result,  setResult]  = useState(null);
  const [error,   setError]   = useState(null);
  const abortRef = useRef(null);

  // Fetch event window when spike changes
  useEffect(() => {
    if (!spike) { setStage("idle"); return; }

    setStage("window-loading");
    setContext(null);
    setTopic(null);
    setResult(null);
    setError(null);

    const ac = new AbortController();
    abortRef.current = ac;

    const cluster = encodeURIComponent(spike.cluster || "Geopolitics");
    const date    = encodeURIComponent(spike.date);

    fetch(`/api/stream/api/event-window/${cluster}/${date}`, { signal: ac.signal })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => {
        if (ac.signal.aborted) return;
        setContext(data);
        setStage("topic-select");
      })
      .catch(e => {
        if (e.name === "AbortError") return;
        setError(`Failed to load event context: ${e.message}`);
        setStage("failed");
      });

    return () => ac.abort();
  }, [spike]);

  // Trigger LLM analysis when user picks a topic
  const handleTopicSelect = useCallback((selectedTopic) => {
    if (!spike) return;
    setTopic(selectedTopic);
    setStage("analyzing");
    setResult(null);
    setError(null);

    fetch("/api/stream/api/analyze-event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        cluster:    spike.cluster,
        event_date: spike.date,
        topic:      selectedTopic,
      }),
    })
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(data => { setResult(data); setStage("done"); })
      .catch(e => { setError(`Analysis failed: ${e.message}`); setStage("failed"); });
  }, [spike]);

  const clusterColor = CLUSTER_COLORS[spike?.cluster] || GOLD;

  return (
    <AnimatePresence>
      {spike && (
        <motion.aside
          key="spike-panel"
          initial={{ x: "100%" }}
          animate={{ x: 0 }}
          exit={{ x: "100%" }}
          transition={{ type: "spring", damping: 28, stiffness: 240 }}
          className="flex flex-col h-full overflow-hidden"
          style={{
            background: "rgba(10,8,6,0.97)",
            borderLeft: `1px solid ${clusterColor}20`,
            width: "100%",
          }}
        >
          {/* ── Header ───────────────────────────────────── */}
          <div
            className="flex-shrink-0 px-5 py-4 flex items-start justify-between"
            style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
          >
            <div className="flex items-start gap-3">
              <div
                className="w-1.5 h-8 flex-shrink-0 mt-0.5"
                style={{ background: clusterColor, boxShadow: `0 0 20px ${clusterColor}50` }}
              />
              <div>
                <p
                  className="text-[9px] font-mono uppercase tracking-[0.3em] mb-0.5"
                  style={{ color: clusterColor }}
                >
                  {spike?.cluster} · Event Intelligence
                </p>
                <p className="text-sm font-mono font-black text-white/90 tracking-wider">
                  {spike?.date}
                </p>
                <p className="text-[9px] font-mono text-white/30 mt-0.5">
                  z = {parseFloat(spike?.z_score || 0).toFixed(2)} · {spike?.post_count} posts
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-white/25 hover:text-white transition-colors text-xl font-mono w-7 h-7 flex items-center justify-center flex-shrink-0"
              style={{ border: "1px solid rgba(255,255,255,0.07)" }}
            >
              ×
            </button>
          </div>

          {/* ── Metrics strip ────────────────────────────── */}
          <div
            className="flex-shrink-0 grid grid-cols-2 gap-px"
            style={{ borderBottom: "1px solid rgba(255,255,255,0.04)" }}
          >
            <MetricBadge
              label="Z-Score"
              value={parseFloat(spike?.z_score || 0).toFixed(2)}
              accent={parseFloat(spike?.z_score || 0) >= 3 ? "#FF4081" : clusterColor}
            />
            <MetricBadge
              label="Posts in Spike"
              value={spike?.post_count ?? "—"}
              accent={clusterColor}
            />
          </div>

          {/* ── Scrollable body ──────────────────────────── */}
          <div className="flex-1 min-h-0 overflow-y-auto px-4 py-4 space-y-5">

            {stage === "window-loading" && (
              <div className="flex items-center gap-3 py-8 justify-center">
                <Spinner color={clusterColor} />
                <span className="text-[10px] font-mono uppercase tracking-widest text-white/35 animate-pulse">
                  Loading event context…
                </span>
              </div>
            )}

            {(stage === "topic-select" || stage === "analyzing" || stage === "done") && context && (
              <>
                <div>
                  <SectionLabel color={clusterColor}>Topic Selection</SectionLabel>
                  <TopicSelector
                    cluster={spike?.cluster}
                    topics={context.topics}
                    onSelect={handleTopicSelect}
                    selected={topic}
                  />
                </div>

                {stage === "analyzing" && (
                  <div className="flex items-center gap-3 py-6 justify-center">
                    <Spinner color={clusterColor} />
                    <span
                      className="text-[10px] font-mono uppercase tracking-widest animate-pulse"
                      style={{ color: clusterColor }}
                    >
                      Generating intelligence brief…
                    </span>
                  </div>
                )}

                {stage === "done" && result && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.3 }}
                    className="space-y-5"
                  >
                    {result.cached && (
                      <div
                        className="text-[9px] font-mono px-2 py-1 inline-flex items-center gap-1.5"
                        style={{ color: "#4CAF50", background: "#4CAF5010", border: "1px solid #4CAF5030" }}
                      >
                        ⚡ Cached result
                      </div>
                    )}

                    <div>
                      <SectionLabel color={clusterColor}>AI Intelligence Brief</SectionLabel>
                      <div
                        className="p-3"
                        style={{ background: "rgba(0,0,0,0.25)", border: `1px solid ${clusterColor}15` }}
                      >
                        <BriefRenderer brief={result.brief} />
                      </div>
                    </div>

                    <div
                      className="flex items-center gap-2 px-3 py-2"
                      style={{ background: "rgba(255,184,0,0.04)", border: "1px solid rgba(255,184,0,0.1)" }}
                    >
                      <span className="text-[9px] font-mono uppercase text-white/30 tracking-widest">
                        Posts Analyzed
                      </span>
                      <span className="text-sm font-mono font-black ml-auto" style={{ color: clusterColor }}>
                        {result.total_posts}
                      </span>
                    </div>

                    {result.top_subreddits?.length > 0 && (
                      <div>
                        <SectionLabel color={clusterColor}>Top Communities</SectionLabel>
                        <SubredditList subreddits={result.top_subreddits} />
                      </div>
                    )}

                    {result.top_domains?.length > 0 && (
                      <div>
                        <SectionLabel color={clusterColor}>Top News Sources</SectionLabel>
                        <DomainList domains={result.top_domains} />
                      </div>
                    )}

                    {result.headline_examples?.length > 0 && (
                      <div>
                        <SectionLabel color={clusterColor}>Representative Headlines</SectionLabel>
                        <HeadlineList headlines={result.headline_examples} />
                      </div>
                    )}
                  </motion.div>
                )}
              </>
            )}

            {stage === "failed" && (
              <div
                className="p-3 text-[11px] font-mono"
                style={{ background: "rgba(239,83,80,0.07)", border: "1px solid rgba(239,83,80,0.25)", color: "#EF9A9A" }}
              >
                ⚠ {error || "An unexpected error occurred."}
                <button
                  className="mt-2 block text-[10px] uppercase tracking-wide underline text-white/40 hover:text-white/70"
                  onClick={() => {
                    if (topic) handleTopicSelect(topic);
                    else if (spike) {
                      setStage("window-loading");
                      setError(null);
                    }
                  }}
                >
                  Retry
                </button>
              </div>
            )}
          </div>

          {/* ── Footer ───────────────────────────────────── */}
          {stage === "topic-select" && (
            <div
              className="flex-shrink-0 px-5 py-2.5"
              style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
            >
              <p className="text-[8px] font-mono uppercase tracking-widest text-white/20">
                {context?.total_posts ?? 0} posts analyzed · ±10 day window
              </p>
            </div>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
