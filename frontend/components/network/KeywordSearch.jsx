"use client";
import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList } from "recharts";

const ACCENT = "#FFB800";
const BORDER = "rgba(255,184,0,0.1)";

export default function KeywordSearch({ onSearch, viewMode = "spread", externalStats = [], externalSources = [] }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);

  const displayStats = results?.keyword_stats || externalStats || [];
  const displaySources = results?.top_sources || externalSources || [];
  const hasExternalOnly = !results && ((externalStats && externalStats.length > 0) || (externalSources && externalSources.length > 0));

  const handleSearch = async (e, specificMode) => {
    e?.preventDefault();
    if (query.length < 2) return;

    setLoading(true);
    const modeToFetch = specificMode || viewMode;
    try {
      const res = await fetch(`/api/network/intelligence/search?q=${encodeURIComponent(query)}&mode=${modeToFetch}`);
      if (res.ok) {
        const data = await res.json();
        setResults(data);
        if (onSearch) onSearch(data);
      }
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleClear = () => {
    setQuery("");
    setResults(null);
    if (onSearch) onSearch(null);
  };

  useEffect(() => {
    if (query.length >= 2 && results) {
        handleSearch(null, viewMode);
    }
  }, [viewMode]);

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* Search Input */}
      <form onSubmit={handleSearch} className="relative group">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search Keyword (e.g. Trump, Biden, Ukraine)..."
          className="w-full bg-white/5 border border-white/10 rounded px-4 py-2.5 text-[11px] font-mono outline-none focus:border-[#FFB800]/50 transition-all placeholder:opacity-30"
        />
        {results ? (
          <button
            type="button"
            onClick={handleClear}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 bg-red-900/50 text-red-200 text-[9px] font-black uppercase tracking-tighter rounded border border-red-500/30 hover:bg-red-800/50 transition-colors"
          >
            Clear
          </button>
        ) : (
          <button
            type="submit"
            disabled={loading}
            className="absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 bg-[#FFB800] text-black text-[9px] font-black uppercase tracking-tighter rounded hover:bg-[#FFB800] transition-colors disabled:opacity-50"
          >
            {loading ? "..." : "Analyze"}
          </button>
        )}
      </form>

      {/* Results Summary */}
      <AnimatePresence>
        {(results || hasExternalOnly) && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex flex-col gap-4"
          >
            {/* Cards (Only for Search results) */}
            {results && (
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: "Posts", val: results.summary.posts },
                  { label: "Communities", val: results.summary.communities },
                  { label: "Connections", val: results.summary.connections },
                ].map((c) => (
                  <div key={c.label} className="bg-white/5 border border-white/5 p-2 rounded flex flex-col items-center">
                    <span className="text-[14px] font-black font-mono text-white">{c.val}</span>
                    <span className="text-[8px] uppercase tracking-widest opacity-40 font-mono">{c.label}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Keyword Bar Chart */}
            <div className="bg-white/5 border border-white/5 p-4 rounded mt-2">
              <h3 className="text-[10px] font-black uppercase tracking-[0.2em] font-mono mb-4 flex items-center gap-2">
                <div className="w-1 h-3 bg-[#FFB800]" />
                {results ? "Search Discovery" : "Top Related Keywords"}
              </h3>
              <div className="h-[200px] w-full mt-4">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={displayStats} layout="vertical" margin={{ left: -20, right: 10 }}>
                    <XAxis type="number" hide />
                    <YAxis
                      dataKey="keyword"
                      type="category"
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#ffffff80", fontSize: 9, fontFamily: "monospace" }}
                      width={80}
                    />
                    <Tooltip
                      contentStyle={{ background: "#0a0806", border: "1px solid rgba(255,184,0,0.2)", fontSize: "10px", fontFamily: "monospace" }}
                      cursor={{ fill: "rgba(255,184,0,0.05)" }}
                    />
                    <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={12}>
                      {displayStats.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={`rgba(255, 184, 0, ${1 - index * 0.08})`} />
                      ))}
                      <LabelList dataKey="count" position="right" fill="#ffffff80" fontSize={9} fontFamily="monospace" offset={8} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Sources Bar Chart */}
            {displaySources.length > 0 && (
              <div className="bg-white/5 border border-white/5 p-4 rounded">
                <h3 className="text-[10px] font-black uppercase tracking-[0.2em] font-mono mb-4 flex items-center gap-2">
                  <div className="w-1 h-3 bg-[#FFB800]" />
                  Top News Sources
                </h3>
                <div className="h-[200px] w-full mt-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={displaySources} layout="vertical" margin={{ left: -20, right: 10 }}>
                      <XAxis type="number" hide />
                      <YAxis
                        dataKey="domain"
                        type="category"
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: "#ffffff80", fontSize: 9, fontFamily: "monospace" }}
                        width={80}
                      />
                      <Tooltip
                        contentStyle={{ background: "#0a0806", border: "1px solid rgba(255,184,0,0.2)", fontSize: "10px", fontFamily: "monospace" }}
                        cursor={{ fill: "rgba(255,184,0,0.05)" }}
                      />
                      <Bar dataKey="count" radius={[0, 4, 4, 0]} barSize={12}>
                        {displaySources.map((entry, index) => (
                          <Cell key={`cell-src-${index}`} fill={`rgba(255, 184, 0, ${1 - index * 0.08})`} />
                        ))}
                        <LabelList dataKey="count" position="right" fill="#ffffff80" fontSize={9} fontFamily="monospace" offset={8} />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
