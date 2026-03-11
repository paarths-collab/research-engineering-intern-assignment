"use client";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function SourceDetailModal({ source, isOpen, subreddit, onClose }) {
    const [intelLoading, setIntelLoading] = useState(false);
    const [intelResult, setIntelResult] = useState(null);
    const [lastSource, setLastSource] = useState(null);

    if (source && source.name !== lastSource) {
        setLastSource(source.name);
        setIntelResult(null);
    }

    if (!source) return null;

    const handleVisitSource = () => {
        const url = source.url || `https://${source.name}`;
        window.open(url, "_blank", "noopener,noreferrer");
    };

    const handleGenerateIntel = async () => {
        setIntelLoading(true);
        setIntelResult(null);
        try {
            const res = await fetch("/api/ai-analysis", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    domain: source.name,
                    subreddit: subreddit,
                    category: source.category,
                    narratives: source.narratives
                }),
            });
            if (res.ok) {
                const json = await res.json();
                setIntelResult(json.analysis || json.result || generateFallback());
            } else {
                setIntelResult(generateFallback());
            }
        } catch {
            setIntelResult(generateFallback());
        } finally {
            setIntelLoading(false);
        }
    };

    const generateFallback = () => {
        const categoryTraits = {
            "News": "a major news outlet with broad audience reach and editorial influence",
            "Blogs": "an independent publishing platform with niche editorial perspectives",
            "Advocacy": "an advocacy-driven publication with a focused policy agenda",
            "Research": "a research institution that produces data-driven, peer-reviewed analysis",
            "Government": "an official government source providing authoritative policy information",
        };
        const trait = categoryTraits[source.category] || "a notable online media source";
        const narrativesStr = (source.narratives || []).slice(0, 2).join(" and ") || "various topics";
        const mentionText = source.loc > 0
            ? "High community reference volumes indicate strong audience engagement."
            : "This source currently has no observed mentions in this community, representing a potential information gap.";

        return `${source.name} is ${trait}. Its primary narratives span ${narrativesStr}. ${mentionText}`;
    };

    return (
        <AnimatePresence>
            {isOpen && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        onClick={onClose}
                        className="absolute inset-0 bg-black/80 backdrop-blur-md"
                    />
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95, y: 10 }}
                        animate={{ opacity: 1, scale: 1, y: 0 }}
                        exit={{ opacity: 0, scale: 0.95, y: 10 }}
                        transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
                        className="glass-panel relative w-full max-w-lg overflow-hidden bg-[#0a0806] border border-white/10 shadow-2xl"
                    >
                        {/* Dramatic Top Accent */}
                        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-[#FFB800] via-[#8B7500] to-transparent" />

                        <div className="p-8">
                            {/* Header Section */}
                            <div className="flex justify-between items-start mb-8">
                                <div>
                                    <span className="inline-block px-2 py-1 bg-[#FFB800]/10 border border-[#FFB800]/20 text-[10px] font-mono text-[#FFB800] uppercase tracking-widest mb-4">
                                        Domain Intel Profile
                                    </span>
                                    <h2 className="text-4xl font-black text-white font-inter tracking-tighter leading-none mb-2">
                                        {source.name}
                                    </h2>
                                    <div className="flex items-center gap-3">
                                        <div className="w-2 h-2 rounded-full bg-[#8B7500] animate-pulse" />
                                        <span className="text-sm font-semibold text-[#8B7500] font-inter uppercase tracking-wide">
                                            {source.category || "General News"}
                                        </span>
                                    </div>
                                </div>
                                <button
                                    onClick={onClose}
                                    className="w-8 h-8 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/10 text-white/40 hover:text-white transition-all border border-white/5 font-mono text-xl leading-none"
                                >
                                    ×
                                </button>
                            </div>

                            {/* Key Metrics Grid */}
                            <div className="grid grid-cols-2 gap-px bg-white/10 border border-white/10 rounded-sm overflow-hidden mb-8">
                                <div className="bg-[#0a0806] p-5 flex flex-col justify-center">
                                    <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest mb-1 block">Community Ref</span>
                                    <span className="text-2xl font-bold font-inter text-white">
                                        {(source.loc !== undefined && source.loc !== null) ? source.loc : "—"}
                                    </span>
                                </div>
                                <div className="bg-[#0a0806] p-5 flex flex-col justify-center">
                                    <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest mb-1 block">Link Visibility</span>
                                    <span className="text-2xl font-bold font-inter text-white">
                                        {(source.p_sub !== undefined && source.p_sub !== null) ? `${(source.p_sub * 100).toFixed(2)}%` : "—"}
                                    </span>
                                </div>
                            </div>

                            {/* Top Narratives */}
                            {source.narratives && source.narratives.length > 0 && (
                                <div className="mb-6 p-5 border border-white/5 rounded-sm bg-gradient-to-br from-white/[0.02] to-transparent">
                                    <span className="text-xs font-bold text-white/60 font-inter uppercase tracking-wider mb-4 flex items-center gap-2">
                                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[#8B7500]"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                                        Prevalent Narratives
                                    </span>
                                    <div className="flex flex-wrap gap-2">
                                        {source.narratives.map((narrative, idx) => (
                                            <span key={idx} className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-full text-xs text-white/90 font-inter shadow-sm">
                                                {narrative}
                                            </span>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* AI Intel Result Panel */}
                            <AnimatePresence>
                                {(intelLoading || intelResult) && (
                                    <motion.div
                                        initial={{ opacity: 0, height: 0 }}
                                        animate={{ opacity: 1, height: "auto" }}
                                        exit={{ opacity: 0, height: 0 }}
                                        className="mb-6 p-4 border border-[#FFB800]/20 bg-[#FFB800]/5 rounded-sm overflow-hidden"
                                    >
                                        <span className="text-[9px] font-mono text-[#FFB800] uppercase tracking-widest block mb-2">
                                            AI Intel Analysis
                                        </span>
                                        {intelLoading ? (
                                            <div className="flex items-center gap-2">
                                                <div className="w-1.5 h-1.5 bg-[#FFB800] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                                                <div className="w-1.5 h-1.5 bg-[#FFB800] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                                                <div className="w-1.5 h-1.5 bg-[#FFB800] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                                                <span className="text-xs text-white/40 font-mono ml-1">Generating...</span>
                                            </div>
                                        ) : (
                                            <p className="text-xs text-white/80 font-inter leading-relaxed">{intelResult}</p>
                                        )}
                                    </motion.div>
                                )}
                            </AnimatePresence>

                            {/* Actions Group */}
                            <div className="flex items-center gap-4 pt-6 border-t border-white/5">
                                <button
                                    onClick={handleVisitSource}
                                    className="flex-1 py-3.5 px-6 border border-[#FFB800]/50 text-[#FFB800] hover:bg-[#FFB800]/10 font-bold font-inter uppercase tracking-wide transition-all text-xs rounded-sm text-center"
                                >
                                    Visit Source ↗
                                </button>
                                <button
                                    onClick={handleGenerateIntel}
                                    disabled={intelLoading}
                                    className="flex-1 py-3.5 px-6 bg-[#FFB800] text-black hover:bg-white font-bold font-inter uppercase tracking-wide transition-all text-xs rounded-sm text-center shadow-[0_0_20px_rgba(255,184,0,0.3)] disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                    {intelLoading ? "Analyzing..." : "Generate Intel"}
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            )}
        </AnimatePresence>
    );
}

