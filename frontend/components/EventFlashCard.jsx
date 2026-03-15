"use client";

function cleanLine(text) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  const stripped = value.replace(/^[-*\d.)\s]+/, "").trim();
  return stripped.length > 170 ? `${stripped.slice(0, 167)}...` : stripped;
}

export default function EventFlashCard({ event, onClose, onAnalyze, loading, error }) {
  if (!event) return null;

  const location = event.location || event.name || event.locations?.[0]?.name || "Unknown";
  const timestamp = event.timestamp
    ? new Date(event.timestamp).toLocaleString()
    : "Unknown";

  const sentimentLabel = event.sentiment || "neutral";
  const subredditLine = event.subreddit
    ? `r/${event.subreddit}`
    : (event.reddit_metrics?.subreddits || []).slice(0, 3).map((s) => `r/${s}`).join(", ") || "N/A";

  const headlineExamples = Array.from(
    new Set((event.headline_examples || [event.title]).map(cleanLine).filter(Boolean))
  ).slice(0, 4);
  const contextDescription = cleanLine(event.summary) || cleanLine(event.strategic_implications?.[0]) || "No additional context available.";

  return (
    <div
      className="absolute left-6 bottom-6 z-30 w-[460px] max-w-[94vw] rounded-2xl backdrop-blur-md"
      style={{
        background: "linear-gradient(180deg, rgba(13,11,8,0.92) 0%, rgba(10,8,6,0.90) 100%)",
        border: "1px solid rgba(255,184,0,0.35)",
        boxShadow: "0 18px 45px rgba(0,0,0,0.5)",
      }}
    >
      <div className="flex items-center justify-between px-4 pt-3">
        <div className="text-[8px] uppercase tracking-[0.24em] font-mono" style={{ color: "#FFB800", opacity: 0.72 }}>
          Event Flash Card
        </div>
        <button onClick={onClose} className="text-[8px] font-mono uppercase tracking-widest" style={{ color: "rgba(255,255,255,0.42)" }}>
          Close
        </button>
      </div>

      <div className="px-4 pb-4 pt-2">
        <h3 className="text-[15px] font-mono font-bold leading-snug" style={{ color: "rgba(255,255,255,0.93)" }}>
          {event.title}
        </h3>

        <div className="mt-3 grid grid-cols-2 gap-y-1.5 text-[10px] font-mono">
          <span style={{ color: "rgba(255,255,255,0.45)" }}>Location</span>
          <span style={{ color: "rgba(255,255,255,0.78)" }}>{location}</span>
          <span style={{ color: "rgba(255,255,255,0.45)" }}>Timestamp</span>
          <span style={{ color: "rgba(255,255,255,0.78)" }}>{timestamp}</span>
          <span style={{ color: "rgba(255,255,255,0.45)" }}>Sentiment</span>
          <span style={{ color: "#FFD54F" }}>{sentimentLabel}</span>
          <span style={{ color: "rgba(255,255,255,0.45)" }}>Sources</span>
          <span style={{ color: "rgba(255,255,255,0.78)" }}>{subredditLine}</span>
        </div>

        <div className="mt-3">
          <div className="text-[8px] uppercase tracking-[0.18em] font-mono mb-1.5" style={{ color: "#FFB800", opacity: 0.75 }}>
            Context
          </div>
          <div className="text-[10px] font-mono leading-relaxed" style={{ color: "rgba(255,255,255,0.74)" }}>
            {contextDescription}
          </div>
        </div>

        <div className="mt-3">
          <div className="text-[8px] uppercase tracking-[0.18em] font-mono mb-1.5" style={{ color: "#FFB800", opacity: 0.75 }}>
            Top Headlines
          </div>
          <ul className="space-y-1.5">
            {headlineExamples.map((headline, i) => (
              <li key={`${headline}-${i}`} className="text-[10px] font-mono leading-snug" style={{ color: "rgba(255,255,255,0.7)" }}>
                • {headline}
              </li>
            ))}
          </ul>
        </div>

        {!!error && (
          <div className="mt-3 text-[9px] font-mono" style={{ color: "#FFA000" }}>
            Analysis failed: {error}
          </div>
        )}

        <button
          onClick={onAnalyze}
          disabled={loading}
          className="mt-4 w-full py-2.5 text-[9px] font-mono uppercase tracking-[0.2em] rounded-lg"
          style={{
            background: loading ? "rgba(255,184,0,0.08)" : "rgba(255,184,0,0.16)",
            border: "1px solid rgba(255,184,0,0.45)",
            color: "#FFB800",
            opacity: loading ? 0.75 : 1,
          }}
        >
          {loading ? "Analyzing Event..." : "Analyze Event"}
        </button>
      </div>
    </div>
  );
}
