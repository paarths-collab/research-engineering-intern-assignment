"use client";
import ReactMarkdown from "react-markdown";

export default function ExecutiveBrief({ brief, loading }) {
  if (loading) {
    return (
      <div className="flex items-center gap-3 py-8 px-2">
        <div className="w-4 h-4 border border-[#FFB800] border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <p className="text-[10px] font-mono text-[#FFB800] animate-pulse tracking-widest uppercase">
          Synthesizing Intelligence Brief...
        </p>
      </div>
    );
  }

  if (!brief) {
    return (
      <p className="text-xs font-mono text-white/25 py-4 px-2">
        No brief available for this spike.
      </p>
    );
  }

  return (
    <div className="px-2 py-1">
      <ReactMarkdown
        components={{
          h1: ({ children }) => (
            <h1 className="text-sm font-mono font-bold text-white tracking-wider uppercase mb-3 pb-2 border-b border-white/10">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-[10px] font-mono font-bold text-[#FFB800] tracking-[0.2em] uppercase mt-5 mb-2">
              ▸ {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-[10px] font-mono font-semibold text-white/50 uppercase mt-3 mb-1">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-[12px] text-[#C8CDD6] leading-relaxed mb-3">
              {children}
            </p>
          ),
          strong: ({ children }) => (
            <strong className="text-[#FFB800] font-semibold">{children}</strong>
          ),
          ul: ({ children }) => (
            <ul className="space-y-1.5 mb-3 ml-1">{children}</ul>
          ),
          li: ({ children }) => (
            <li className="text-[12px] text-[#C8CDD6] flex items-start gap-2">
              <span className="text-[#FFB800] mt-0.5 flex-shrink-0">•</span>
              <span>{children}</span>
            </li>
          ),
          hr: () => <hr className="border-white/8 my-3" />,
          em: ({ children }) => (
            <em className="text-white/40 not-italic text-[10px] font-mono">{children}</em>
          ),
          code: ({ children }) => (
            <code className="text-[#FFB800] bg-[rgba(255,184,0,0.08)] px-1.5 py-0.5 text-[10px] font-mono">
              {children}
            </code>
          ),
        }}
      >
        {brief}
      </ReactMarkdown>
    </div>
  );
}
