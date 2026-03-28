"use client";

import { useState } from "react";

const PANEL = {
  background: "rgba(10, 8, 6, 0.4)",
  backdropFilter: "blur(20px)",
  border: "1px solid rgba(255, 184, 0, 0.08)",
  borderRadius: "0px",
};

const INNER = {
  background: "rgba(0, 0, 0, 0.2)",
  border: "1px solid rgba(255, 255, 255, 0.03)",
  borderRadius: "0px",
};

const EXAMPLES = [
  "Which subreddit has the highest echo-chamber lift in the dataset?",
  "What are the top domains by frequency across subreddit_domain_flow_v2?",
  "Which narratives show the strongest spread_strength in narrative_intelligence_summary?",
  "Why might volume peaks in daily_volume_v2 align with narrative surges? (use web search)",
];

function MaximizeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
    </svg>
  );
}

function ChartPanel({ title, badge, onMaximize, children, className = "" }) {
  return (
    <section className={`flex flex-col min-h-0 ${className}`} style={PANEL}>
      <div className="flex items-center gap-3 px-4 pt-4 pb-2 flex-shrink-0">
        <div className="w-1.5 h-6 bg-[#FFB800]" style={{ boxShadow: "0 0 15px rgba(255, 184, 0, 0.3)" }} />
        <h2 className="text-[11px] font-black uppercase tracking-[0.15em] text-white/90 font-manrope">{title}</h2>
        {badge ? (
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
        ) : null}
        <button onClick={onMaximize} className="ml-2 p-1.5 text-white/20 hover:text-[#FFB800] transition-colors">
          <MaximizeIcon />
        </button>
      </div>
      <div className="flex-1 min-h-0 m-2 overflow-hidden border border-white/5" style={INNER}>
        {children}
      </div>
    </section>
  );
}

function MaxModal({ title, badge, onClose, children }) {
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-8 bg-black/90 backdrop-blur-xl" onClick={onClose}>
      <div
        className="w-full max-w-6xl h-full max-h-[92vh] flex flex-col shadow-[0_0_100px_rgba(255,184,0,0.1)]"
        style={PANEL}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-4 px-6 py-5 border-b border-white/5">
          <div className="w-2 h-8 bg-[#FFB800]" />
          <span className="text-xl font-black uppercase tracking-widest text-white font-inter">{title}</span>
          {badge ? (
            <span className="text-[10px] font-bold px-3 py-1 bg-[#8B7500]/10 text-[#8B7500] border border-[#8B7500]/20 font-mono">
              {badge}
            </span>
          ) : null}
          <button onClick={onClose} className="ml-auto text-3xl font-mono text-white/20 hover:text-white transition-colors">
            x
          </button>
        </div>
        <div className="flex-1 min-h-0 m-6 border border-white/5" style={INNER}>
          {children}
        </div>
      </div>
    </div>
  );
}

function QueryPanel({ query, setQuery, loading, runQuery, debug, setDebug, webSearch, setWebSearch }) {
  return (
    <div className="h-full p-4 flex flex-col gap-3">
      <textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        rows={7}
        className="w-full resize-none bg-black/30 border border-white/15 px-3 py-2 text-sm text-white focus:outline-none focus:border-[#FFB800]/70"
      />

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((item, idx) => (
          <button
            key={item}
            onClick={() => setQuery(item)}
            className="text-[10px] px-2 py-1 border border-white/15 text-white/65 hover:text-white hover:border-[#FFB800]/50"
            title={item}
          >
            EXAMPLE {idx + 1}
          </button>
        ))}
      </div>

      <label className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-white/55 font-mono">
        <input type="checkbox" checked={debug} onChange={(e) => setDebug(e.target.checked)} />
        Debug Mode
      </label>

      <label className="inline-flex items-center gap-2 text-[10px] uppercase tracking-[0.14em] text-white/55 font-mono">
        <input type="checkbox" checked={webSearch} onChange={(e) => setWebSearch(e.target.checked)} />
        Web Search (DuckDuckGo + Scrape)
      </label>

      <button
        onClick={runQuery}
        disabled={loading}
        className="mt-auto px-4 py-2 text-sm font-black uppercase tracking-[0.16em] border border-[#FFB800]/50 bg-[#FFB800]/10 text-[#FFB800] hover:bg-[#FFB800]/20 disabled:opacity-60"
      >
        {loading ? "Running..." : "Run Query"}
      </button>
    </div>
  );
}

function AnswerPanel({ result, error }) {
  return (
    <div className="h-full p-4 overflow-auto">
      {error ? <p className="text-sm text-red-300">{error}</p> : null}
      {!result && !error ? <p className="text-sm text-white/50">Ask a query to get a grounded response.</p> : null}
      {result?.answer ? <p className="text-sm leading-relaxed text-white/85 whitespace-pre-wrap">{result.answer}</p> : null}
    </div>
  );
}

export default function ChatbotPage() {
  const [query, setQuery] = useState(EXAMPLES[0]);
  const [loading, setLoading] = useState(false);
  const [debug, setDebug] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [maximized, setMaximized] = useState(null);
  const [webSearch, setWebSearch] = useState(false);

  const PANELS = {
    query: { title: "Query Console", badge: webSearch ? "DATASET + WEB" : "DATASET_CHAT" },
    answer: { title: "Answer", badge: null },
  };

  async function runQuery() {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/chatbot/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, debug, web_search: webSearch }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail || `Request failed (${res.status})`);
      setResult(data);
    } catch (err) {
      setError(err.message || "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-screen max-h-screen overflow-hidden flex flex-col bg-[#0a0806] font-inter text-[#e6eaf0]">
      <header className="flex-shrink-0 px-8 py-5 flex items-center justify-between border-b border-white/5 bg-black/30">
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-2 bg-gradient-to-r from-[#FFB800] to-[#8B7500] opacity-20 blur-lg animate-pulse" />
            <div className="relative h-10 w-1 bg-white" />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-[10px] uppercase font-bold tracking-[0.4em] text-[#8B7500] font-mono">
                System.Narrative.Chatbot
              </span>
              <div className="h-px w-12 bg-white/10" />
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 bg-[#FFB800] animate-ping rounded-full" />
                <span className="text-[10px] uppercase font-bold text-white/40 font-mono">Inference Loop Active</span>
              </div>
            </div>
            <h1 className="text-3xl font-black uppercase tracking-tighter leading-none text-white">
              Chatbot Intelligence Console
            </h1>
          </div>
        </div>
      </header>

      <main className="flex-1 min-h-0 flex flex-col p-4">
        <div className="flex gap-2 mb-4 overflow-x-auto pb-2 shrink-0 scrollbar-hide">
          {EXAMPLES.map((item, idx) => (
            <button
              key={item}
              onClick={() => setQuery(item)}
              className={`px-4 py-1.5 font-mono text-xs uppercase tracking-widest border transition-all flex-shrink-0 ${
                query === item
                  ? "bg-[#FFB800] text-black border-[#FFB800] font-bold"
                  : "bg-transparent text-white/40 border-white/10 hover:border-white/30 hover:text-white"
              }`}
              title={item}
            >
              Q{idx + 1}
            </button>
          ))}
        </div>

        <div className="flex-1 min-h-0 grid grid-cols-12 gap-4">
          <div className="col-span-12 lg:col-span-4 flex flex-col gap-4 min-h-0">
            <ChartPanel {...PANELS.query} className="flex-1 min-h-0" onMaximize={() => setMaximized("query")}>
              <QueryPanel
                query={query}
                setQuery={setQuery}
                loading={loading}
                runQuery={runQuery}
                debug={debug}
                setDebug={setDebug}
                webSearch={webSearch}
                setWebSearch={setWebSearch}
              />
            </ChartPanel>
          </div>

          <div className="col-span-12 lg:col-span-8 flex flex-col gap-4 min-h-0">
            <ChartPanel {...PANELS.answer} className="flex-1 min-h-0" onMaximize={() => setMaximized("answer")}>
              <AnswerPanel result={result} error={error} />
            </ChartPanel>
          </div>
        </div>
      </main>

      {maximized ? (
        <MaxModal {...PANELS[maximized]} onClose={() => setMaximized(null)}>
          {maximized === "query" ? (
            <QueryPanel
              query={query}
              setQuery={setQuery}
              loading={loading}
              runQuery={runQuery}
              debug={debug}
              setDebug={setDebug}
              webSearch={webSearch}
              setWebSearch={setWebSearch}
            />
          ) : null}
          {maximized === "answer" ? <AnswerPanel result={result} error={error} /> : null}
        </MaxModal>
      ) : null}
    </div>
  );
}
