"use client";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

const MOCK_BRIEF = `# Media Ecosystem Intelligence Summary

**Classification:** UNCLASSIFIED // FOUO  
**Analysis Period:** T-30 days  
**Subject:** Subreddit Narrative Polarization Index

---

## Executive Summary

The subreddit **r/politics** demonstrates the highest ecosystem isolation score (0.82), indicating a strongly self-reinforcing media diet among its subscribers. Cross-platform signal amplification is primarily driven by three domain clusters: mainstream news outlets, advocacy organizations, and social amplifiers.

## Key Findings

- **Echo Chamber Severity:** r/politics and r/conspiracy exhibit near-total ideological isolation, with minimal narrative crossover detected.
- **Lift Amplifiers:** Twitter.com (lift: 5.1×) and r/conspiracy (isolation: 0.91) represent the highest-risk signal amplification nodes in the current analysis window.
- **Domain Penetration:** nytimes.com leads in raw mention frequency (120 refs) but is eclipsed by twitter.com in amplification efficiency.

## Similarity Cluster Analysis

| Subreddit | Closest Match | Similarity |
|---|---|---|
| r/politics | r/news | 0.65 |
| r/worldnews | r/news | 0.79 |
| r/conspiracy | r/geopolitics | 0.31 |

## Risk Assessment

The current media ecosystem map indicates **moderate-to-high polarization** across observed subreddits. The r/conspiracy community operates in near-complete informational isolation, with a similarity score below 0.25 relative to all other monitored subreddits.

Recommended monitoring cadence: **48-hour refresh cycle** for high-risk nodes.

---

*NarrativeSignal · POLARIZE Module · Auto-generated intelligence brief*
`;

export default function IntelligenceBrief({ subreddit = "politics" }) {
  const [brief, setBrief] = useState("");
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    const fetchBrief = async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/intelligence-brief", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ subreddit }),
        });
        const json = await res.json();
        setBrief(json.brief || MOCK_BRIEF);
      } catch {
        setBrief(MOCK_BRIEF);
      } finally {
        setLoading(false);
      }
    };
    fetchBrief();
  }, [subreddit]);

  return (
    <div className="bg-[#0c0c0e] border border-[#1f1f23] rounded-none">
      {/* Header */}
      <div className="border-b border-[#1f1f23] px-4 py-3 flex items-center justify-between">
        <div>
          <p className="text-[10px] font-mono text-[#3b82f6] tracking-[0.2em] uppercase">
            Module 04
          </p>
          <h2 className="text-sm font-mono text-white tracking-widest uppercase mt-0.5">
            Intelligence Brief
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 border border-[#1d4ed8]/30 px-2 py-1">
            <span className="w-1.5 h-1.5 bg-[#3b82f6] rounded-full" />
            <span className="text-[9px] font-mono text-[#3b82f6]">AI GENERATED</span>
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[9px] font-mono text-[#52525b] hover:text-white border border-[#27272a] hover:border-[#52525b] px-2 py-1 transition-colors"
          >
            {expanded ? "COLLAPSE" : "EXPAND"}
          </button>
        </div>
      </div>

      {/* Content */}
      <div
        className={`px-6 py-5 overflow-hidden transition-all duration-500 ${expanded ? "max-h-[9999px]" : "max-h-96"
          }`}
      >
        {loading ? (
          <div className="flex items-center gap-3 py-8">
            <div className="w-4 h-4 border border-[#3b82f6] border-t-transparent rounded-full animate-spin flex-shrink-0" />
            <p className="text-[10px] font-mono text-[#3b82f6] animate-pulse tracking-widest">
              SYNTHESIZING INTELLIGENCE BRIEF...
            </p>
          </div>
        ) : (
          <div className="prose-intelligence">
            <ReactMarkdown
              components={{
                h1: ({ children }) => (
                  <h1 className="text-base font-mono font-bold text-white tracking-wider uppercase mb-4 pb-2 border-b border-[#1f1f23]">
                    {children}
                  </h1>
                ),
                h2: ({ children }) => (
                  <h2 className="text-xs font-mono font-bold text-[#60a5fa] tracking-widest uppercase mt-6 mb-2">
                    ▸ {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-xs font-mono font-semibold text-[#a1a1aa] uppercase mt-4 mb-1">
                    {children}
                  </h3>
                ),
                p: ({ children }) => (
                  <p className="text-xs font-mono text-[#71717a] leading-relaxed mb-3">
                    {children}
                  </p>
                ),
                strong: ({ children }) => (
                  <strong className="text-white font-bold">{children}</strong>
                ),
                ul: ({ children }) => (
                  <ul className="space-y-1 mb-3 ml-0">{children}</ul>
                ),
                li: ({ children }) => (
                  <li className="text-xs font-mono text-[#71717a] flex items-start gap-2">
                    <span className="text-[#3b82f6] mt-0.5 flex-shrink-0">·</span>
                    <span>{children}</span>
                  </li>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto my-4">
                    <table className="w-full border-collapse text-xs font-mono">
                      {children}
                    </table>
                  </div>
                ),
                thead: ({ children }) => (
                  <thead className="border-b border-[#1f1f23]">{children}</thead>
                ),
                th: ({ children }) => (
                  <th className="text-left py-2 px-3 text-[9px] text-[#3b82f6] tracking-widest uppercase">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="py-1.5 px-3 text-[#71717a] border-b border-[#0f0f10]">
                    {children}
                  </td>
                ),
                tr: ({ children }) => (
                  <tr className="hover:bg-[#111113] transition-colors">{children}</tr>
                ),
                hr: () => <hr className="border-[#1f1f23] my-4" />,
                em: ({ children }) => (
                  <em className="text-[#52525b] not-italic text-[10px]">{children}</em>
                ),
                code: ({ children }) => (
                  <code className="text-[#3b82f6] bg-[#0f172a] px-1.5 py-0.5 text-[10px]">
                    {children}
                  </code>
                ),
              }}
            >
              {brief}
            </ReactMarkdown>
          </div>
        )}
      </div>

      {/* Fade + expand hint */}
      {!expanded && !loading && (
        <div className="relative">
          <div className="absolute -top-16 left-0 right-0 h-16 bg-gradient-to-t from-[#0c0c0e] to-transparent pointer-events-none" />
          <div className="border-t border-[#1f1f23] px-4 py-2 text-center">
            <button
              onClick={() => setExpanded(true)}
              className="text-[9px] font-mono text-[#3b82f6] hover:text-white transition-colors tracking-widest"
            >
              ↓ READ FULL INTELLIGENCE BRIEF
            </button>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="border-t border-[#1f1f23] px-4 py-2 flex justify-between">
        <span className="text-[9px] font-mono text-[#27272a]">
          GENERATED BY NARRATIVESIGNAL LLM ENGINE
        </span>
        <span className="text-[9px] font-mono text-[#27272a]">
          CLASSIFICATION: UNCLASSIFIED
        </span>
      </div>
    </div>
  );
}
