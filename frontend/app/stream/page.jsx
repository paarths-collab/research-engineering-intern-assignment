"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import NarrativeTimelineChart from "@/components/stream/NarrativeTimelineChart";

const ACCENT = "#FFB800";
const GOLD   = "#8B7500";
const CRIT   = "#FF4081";
const BG     = "#0a0806";

function addDays(dateStr, n) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function SectionHeader({ label, badge, accent = ACCENT }) {
  return (
    <div className="flex items-center gap-3 px-5 py-3"
      style={{ borderBottom: "1px solid rgba(255,184,0,0.06)" }}>
      <div className="w-1 h-5 flex-shrink-0" style={{ background: accent, boxShadow: `0 0 8px ${accent}55` }} />
      <h2 className="text-[11px] font-black uppercase tracking-[0.2em] font-mono" style={{ color: accent }}>
        {label}
      </h2>
      {badge && (
        <span className="text-[9px] font-mono px-1.5 py-0.5 ml-auto"
          style={{ color: accent, background: `${accent}10`, border: `1px solid ${accent}25` }}>
          {badge}
        </span>
      )}
    </div>
  );
}

function Spinner({ color = ACCENT }) {
  return (
    <div className="w-5 h-5 border-2 border-t-transparent rounded-full animate-spin flex-shrink-0"
      style={{ borderColor: `${color}aa transparent ${color}aa ${color}aa` }} />
  );
}

const SENTIMENT_COLOR = {
  outrage:     "#FF4081",
  alarm:       "#FFB800",
  celebratory: "#FFB800",
  skeptical:   "#B388FF",
  neutral:     "rgba(255,255,255,0.3)",
};

function TopicCard({ topic, isSelected, onClick }) {
  const sentColor = SENTIMENT_COLOR[topic.sentiment] || SENTIMENT_COLOR.neutral;
  return (
    <motion.button layout whileHover={{ scale: 1.01 }} onClick={onClick}
      className="w-full text-left px-4 py-3 transition-all"
      style={{
        background: isSelected ? `${ACCENT}10` : "rgba(255,184,0,0.02)",
        border:     `1px solid ${isSelected ? `${ACCENT}45` : "rgba(255,184,0,0.08)"}`,
        boxShadow:  isSelected ? `0 0 18px ${ACCENT}15` : "none",
      }}>
      <p className="text-[12px] font-semibold text-white/90 leading-snug mb-2">{topic.topic}</p>
      {topic.key_claim && (
        <p className="text-[10px] text-white/50 leading-snug mb-2 italic">{topic.key_claim}</p>
      )}
      <div className="flex flex-wrap items-center gap-1 mt-1">
        {topic.sentiment && (
          <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 uppercase tracking-wide"
            style={{ background: `${sentColor}15`, color: sentColor, border: `1px solid ${sentColor}40` }}>
            {topic.sentiment}
          </span>
        )}
        {topic.subreddits?.map(s => (
          <span key={s} className="text-[9px] font-mono px-1.5 py-0.5"
            style={{ background: "rgba(255,184,0,0.07)", color: ACCENT, border: "1px solid rgba(255,184,0,0.15)" }}>
            r/{s}
          </span>
        ))}
      </div>
      {topic.example_headlines?.length > 0 && (
        <ul className="mt-2 space-y-1">
          {topic.example_headlines.slice(0, 3).map((h, i) => (
            <li key={i} className="text-[9px] leading-snug truncate"
              style={{ color: "rgba(255,255,255,0.3)", borderLeft: "2px solid rgba(255,184,0,0.15)", paddingLeft: 6 }}>
              {h}
            </li>
          ))}
        </ul>
      )}
    </motion.button>
  );
}

function StatBadge({ label, value, accent = ACCENT }) {
  return (
    <div className="flex flex-col px-4 py-2.5"
      style={{ borderRight: "1px solid rgba(255,184,0,0.06)" }}>
      <span className="text-lg font-black font-mono leading-none" style={{ color: accent }}>{value}</span>
      <span className="text-[9px] font-mono uppercase tracking-widest text-white/30 mt-0.5">{label}</span>
    </div>
  );
}



export default function StreamPage() {
  const [volumeData,      setVolumeData]      = useState(null);
  const [loading,         setLoading]         = useState(true);
  const [chartError,      setChartError]      = useState(null);
  const [selectedDate,    setSelectedDate]    = useState(null);
  const [topicsLoading,   setTopicsLoading]   = useState(false);
  const [topicsError,     setTopicsError]     = useState(null);
  const [topics,          setTopics]          = useState(null);
  const [selectedTopic,   setSelectedTopic]   = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError,   setAnalysisError]   = useState(null);
  const [analysis,        setAnalysis]        = useState(null);

  const topicsSectionRef = useRef(null);
  const briefSectionRef  = useRef(null);

  // ── Load timeline volume ────────────────────────────────
  useEffect(() => {
    fetch("/api/stream/api/timeline-volume")
      .then(r => r.json())
      .then(d => { setVolumeData(d); setLoading(false); })
      .catch(() => { setChartError("Failed to load timeline data."); setLoading(false); });
  }, []);

  const spikes         = volumeData?.spikes || [];
  const criticalSpikes  = spikes.filter(s => (s.post_count || 0) >= 100);
  const subredditCount  = volumeData?.series ? Object.keys(volumeData.series).length : 0;
  const totalPoints     = volumeData?.series
    ? Object.values(volumeData.series).reduce((a, v) => a + v.length, 0)
    : 0;

  // Stage 1: date click → extract topics
  const handleDateClick = useCallback(async (dateStr) => {
    setSelectedDate(dateStr);
    setTopics(null);
    setTopicsError(null);
    setTopicsLoading(true);
    setSelectedTopic(null);
    setAnalysis(null);
    setAnalysisError(null);
    try {
      const res = await fetch("/api/stream/api/extract-topics", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ start_date: addDays(dateStr, -10), end_date: addDays(dateStr, +10) }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTopics(data.topics || []);
      setTimeout(() => topicsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e) {
      setTopicsError(e.message || "Topic extraction failed.");
    } finally {
      setTopicsLoading(false);
    }
  }, []);

  // Stage 2: topic click → narrative analysis
  const handleTopicClick = useCallback(async (topicStr) => {
    if (!selectedDate) return;
    setSelectedTopic(topicStr);
    setAnalysis(null);
    setAnalysisError(null);
    setAnalysisLoading(true);
    try {
      const res = await fetch("/api/stream/api/topic-analysis", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          topic:      topicStr,
          start_date: addDays(selectedDate, -5),
          end_date:   addDays(selectedDate, +5),
        }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAnalysis(data);
      setTimeout(() => briefSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e) {
      setAnalysisError(e.message || "Analysis failed.");
    } finally {
      setAnalysisLoading(false);
    }
  }, [selectedDate]);

  return (
    <div className="min-h-screen flex flex-col font-mono" style={{ background: BG, color: "#e6eaf0" }}>

      {/* ── Header ─────────────────────────────────────── */}
      <header className="flex-shrink-0 px-8 py-5 flex items-center justify-between"
        style={{ borderBottom: "1px solid rgba(255,184,0,0.07)", background: "rgba(0,0,0,0.4)" }}>
        <div className="flex items-center gap-5">
          <div className="relative">
            <div className="absolute -inset-2 opacity-20 blur-lg animate-pulse"
              style={{ background: `linear-gradient(to right, ${ACCENT}, transparent)` }} />
            <div className="relative h-10 w-1" style={{ background: ACCENT }} />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-[9px] uppercase font-bold tracking-[0.4em]" style={{ color: `${ACCENT}55` }}>
                NarrativeSignal · 10 Subreddits · Aggregate Volume
              </span>
            </div>
            <h1 className="text-3xl font-black uppercase tracking-tighter leading-none text-white">
              Narrative Timeline
            </h1>
          </div>
        </div>
        <div className="flex items-stretch" style={{ border: `1px solid ${ACCENT}15`, background: "rgba(5,7,10,0.6)" }}>
          <StatBadge label="Subreddits"  value={subredditCount || "—"} />
          <StatBadge label="Spikes"      value={spikes.length || "—"} accent={spikes.length > 5 ? CRIT : ACCENT} />
          <StatBadge label="Critical"    value={criticalSpikes.length || "—"} accent={criticalSpikes.length > 0 ? CRIT : "rgba(255,255,255,0.2)"} />
          <StatBadge label="Data Points" value={totalPoints || "—"} accent="rgba(255,255,255,0.3)" />
        </div>
      </header>

      {/* ── Main Body ────────────────────────────────────── */}
      <main className="flex-1 flex flex-col gap-0">

        {/* ── Section 1: Timeline ─────────────────────── */}
        <section style={{ background: "rgba(0,0,0,0.2)", borderBottom: "1px solid rgba(255,184,0,0.07)" }}>
          <SectionHeader label="Narrative Timeline" badge="TOTAL DAILY VOLUME · D3" />
          <div className="px-5 py-2 flex items-center gap-3"
            style={{ borderBottom: "1px solid rgba(255,184,0,0.04)" }}>
            <p className="text-[9px] uppercase tracking-widest text-white/20">
              Click anywhere on the chart to extract narrative topics · spike markers show z-score anomalies
            </p>
            {selectedDate && (
              <span className="text-[10px] font-bold px-2 py-0.5 ml-auto"
                style={{ color: ACCENT, background: `${ACCENT}10`, border: `1px solid ${ACCENT}30` }}>
                ▸ {selectedDate}
              </span>
            )}
          </div>

          <div className="mx-3 my-3" style={{ height: "340px", background: "rgba(255,184,0,0.01)", border: "1px solid rgba(255,184,0,0.06)" }}>
            {loading ? (
              <div className="h-full flex items-center justify-center gap-3">
                <Spinner />
                <span className="text-[10px] uppercase tracking-widest animate-pulse" style={{ color: ACCENT }}>
                  Loading narrative data…
                </span>
              </div>
            ) : chartError ? (
              <div className="h-full flex items-center justify-center">
                <p className="text-xs text-white/30">{chartError}</p>
              </div>
            ) : (
              <NarrativeTimelineChart volumeData={volumeData} onDateClick={handleDateClick} />
            )}
          </div>

          {/* Spike chip strip */}
          {!loading && spikes.length > 0 && (
            <div className="px-4 pb-3 flex items-center gap-2 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
              <span className="text-[9px] uppercase tracking-widest text-white/20 flex-shrink-0">Spikes →</span>
              {spikes.slice(0, 16).map(s => {
                const isCrit = (s.post_count || 0) >= 100;
                const col    = isCrit ? CRIT : GOLD;
                const isSel  = selectedDate === s.date;
                return (
                  <button key={s.date} onClick={() => handleDateClick(s.date)}
                    className="flex-shrink-0 px-2.5 py-1 text-[9px] font-bold uppercase tracking-wide transition-all"
                    style={{
                      background: isSel ? `${col}18` : "rgba(255,255,255,0.02)",
                      border:     `1px solid ${isSel ? `${col}60` : "rgba(255,255,255,0.06)"}`,
                      color:      isSel ? col : "rgba(255,255,255,0.25)",
                    }}>
                    {s.date}
                    <span className="ml-1.5" style={{ color: col, opacity: 0.8 }}>
                      z={parseFloat(s.z_score).toFixed(1)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* ── Section 2: Detected Topics ──────────────── */}
        <AnimatePresence>
          {(topicsLoading || topics !== null) && (
            <motion.section key="topics" ref={topicsSectionRef}
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              style={{ borderBottom: "1px solid rgba(255,184,0,0.07)" }}>
              <SectionHeader
                label="Detected Narrative Topics"
                badge={selectedDate ? `±10d window · ${selectedDate}` : "LLM_STAGE_1"}
                accent={ACCENT}
              />
              <div className="px-5 py-4">
                {topicsLoading && (
                  <div className="flex items-center justify-center gap-3 py-6">
                    <Spinner />
                    <span className="text-[10px] uppercase tracking-widest animate-pulse text-white/40">
                      Extracting narrative topics via LLM…
                    </span>
                  </div>
                )}
                {topicsError && !topicsLoading && (
                  <div className="px-4 py-3 text-[11px]"
                    style={{ background: "rgba(239,83,80,0.07)", border: "1px solid rgba(239,83,80,0.2)", color: "#EF9A9A" }}>
                    ⚠ {topicsError}
                  </div>
                )}
                {topics && !topicsLoading && topics.length === 0 && (
                  <p className="text-[10px] text-white/20 py-4 text-center uppercase tracking-widest">
                    No topics extracted for this window
                  </p>
                )}
                {topics && !topicsLoading && topics.length > 0 && (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {topics.map((t, i) => (
                      <TopicCard key={i} topic={t}
                        isSelected={selectedTopic === t.topic}
                        onClick={() => handleTopicClick(t.topic)} />
                    ))}
                  </div>
                )}
              </div>
            </motion.section>
          )}
        </AnimatePresence>

        {/* ── Section 3: Intelligence Brief ───────────── */}
        <AnimatePresence>
          {(analysisLoading || analysis) && (
            <motion.section key="brief" ref={briefSectionRef}
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.2, delay: 0.05 }}>
              <SectionHeader label="Narrative Intelligence Brief" badge="LLM · STAGE 2" accent={GOLD} />
              <div className="px-5 py-4">
                {analysisLoading && (
                  <div className="flex items-center justify-center gap-3 py-8">
                    <Spinner color={GOLD} />
                    <span className="text-[10px] uppercase tracking-widest animate-pulse" style={{ color: GOLD }}>
                      Generating intelligence brief…
                    </span>
                  </div>
                )}
                {analysisError && !analysisLoading && (
                  <div className="px-4 py-3 text-[11px]"
                    style={{ background: "rgba(239,83,80,0.07)", border: "1px solid rgba(239,83,80,0.2)", color: "#EF9A9A" }}>
                    ⚠ {analysisError}
                  </div>
                )}
                {analysis && !analysisLoading && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="px-3 py-2 flex-1"
                        style={{ background: `${GOLD}07`, border: `1px solid ${GOLD}18` }}>
                        <p className="text-[9px] uppercase tracking-widest text-white/25 mb-1">Analyzed Topic</p>
                        <p className="text-sm font-semibold text-white/90">{analysis.topic}</p>
                      </div>
                      {analysis.cached && (
                        <span className="text-[9px] px-2 py-1 flex-shrink-0"
                          style={{ color: "#4CAF50", background: "#4CAF5010", border: "1px solid #4CAF5030" }}>
                          ⚡ cached
                        </span>
                      )}
                    </div>

                    <div className="p-4" style={{ background: "rgba(0,0,0,0.3)", border: `1px solid ${GOLD}10` }}>
                      <div className="prose prose-invert prose-sm max-w-none"
                        style={{ "--tw-prose-headings": GOLD, "--tw-prose-body": "rgba(255,255,255,0.78)" }}>
                        <ReactMarkdown>{analysis.brief}</ReactMarkdown>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-1">
                      {[
                        { l: "Posts Analyzed", v: analysis.total_posts },
                        { l: "Top Community",  v: analysis.top_subreddits?.[0]?.[0] ? `r/${analysis.top_subreddits[0][0]}` : "—" },
                        { l: "Top Source",     v: analysis.top_domains?.[0]?.[0] || "—" },
                        { l: "Bridge Authors", v: analysis.bridge_authors?.length ?? 0 },
                      ].map(({ l, v }) => (
                        <div key={l} className="flex flex-col items-center py-3"
                          style={{ background: `${GOLD}05`, border: `1px solid ${GOLD}10` }}>
                          <span className="text-base font-black" style={{ color: GOLD }}>{v}</span>
                          <span className="text-[8px] uppercase tracking-widest text-white/25 mt-0.5">{l}</span>
                        </div>
                      ))}
                    </div>

                    {analysis.top_subreddits?.length > 0 && (
                      <div>
                        <p className="text-[9px] uppercase tracking-widest text-white/25 mb-2">Top Communities</p>
                        <div className="flex flex-wrap gap-2">
                          {analysis.top_subreddits.map(([sub, cnt]) => (
                            <div key={sub} className="flex items-center gap-1.5 px-2.5 py-1"
                              style={{ background: `${ACCENT}07`, border: `1px solid ${ACCENT}18` }}>
                              <span className="text-[10px]" style={{ color: ACCENT }}>r/{sub}</span>
                              <span className="text-[9px] text-white/25">{cnt}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {analysis.top_domains?.length > 0 && (
                      <div>
                        <p className="text-[9px] uppercase tracking-widest text-white/25 mb-2">Key Sources</p>
                        <div className="flex flex-wrap gap-2">
                          {analysis.top_domains.map(([domain, cnt]) => (
                            <div key={domain} className="flex items-center gap-1.5 px-2.5 py-1"
                              style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)" }}>
                              <span className="text-[10px] text-white/55">{domain}</span>
                              <span className="text-[9px] text-white/20">{cnt}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {analysis.bridge_authors?.length > 0 && (
                      <div>
                        <p className="text-[9px] uppercase tracking-widest text-white/25 mb-2">Bridge Authors</p>
                        <div className="flex flex-wrap gap-2">
                          {analysis.bridge_authors.map(author => (
                            <div key={author} className="flex items-center gap-1 px-2.5 py-1"
                              style={{ background: `${GOLD}07`, border: `1px solid ${GOLD}18` }}>
                              <span className="text-[10px] font-mono" style={{ color: GOLD }}>u/{author}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </div>
            </motion.section>
          )}
        </AnimatePresence>

        {/* ── Empty state ──────────────────────────────── */}
        {!selectedDate && !loading && !chartError && (
          <div className="flex flex-col items-center justify-center py-14 gap-3">
            <div className="w-12 h-12 flex items-center justify-center text-2xl"
              style={{ border: `1px solid ${ACCENT}18`, color: `${ACCENT}35` }}>↑</div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-white/15">
              Click the timeline to begin narrative analysis
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
