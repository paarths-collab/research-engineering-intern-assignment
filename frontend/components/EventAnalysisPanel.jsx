"use client";

function toBulletLines(text) {
  if (!text || typeof text !== "string") return [];
  return text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => line.replace(/^[-*\d.)\s]+/, ""));
}

function extractSections(report) {
  if (!report || typeof report !== "string") return [];

  const blocks = report.split(/\n\s*\n/g).map((b) => b.trim()).filter(Boolean);
  return blocks.map((block, i) => {
    const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
    const first = lines[0] || "";
    const isHeading = /[:]/.test(first) && first.length < 90;
    const title = isHeading ? first.replace(/:$/, "") : `Section ${i + 1}`;
    const body = isHeading ? lines.slice(1).join("\n") : lines.join("\n");
    return { title, bodyLines: toBulletLines(body) };
  });
}

function Section({ title, children }) {
  return (
    <div className="mt-5">
      <div className="text-[8px] uppercase tracking-[0.22em] font-mono mb-2" style={{ color: "#FFB800", opacity: 0.74 }}>
        {title}
      </div>
      <div className="text-[10px] font-mono leading-relaxed" style={{ color: "rgba(255,255,255,0.72)" }}>
        {children}
      </div>
    </div>
  );
}

export default function EventAnalysisPanel({ event, analysis, onClose, onBack }) {
  if (!event || !analysis) return null;

  const reddit = analysis.reddit_context || {};
  const news = analysis.news_context || {};
  const reportSections = extractSections(analysis.analysis_report);
  const keyFacts = [
    { label: "Event", value: event.title || "N/A" },
    { label: "Sentiment", value: event.sentiment || "neutral" },
    {
      label: "Sentiment score",
      value: typeof event.sentiment_score === "number" ? event.sentiment_score.toFixed(2) : "N/A",
    },
    { label: "Related subreddits", value: (reddit.related_subreddits || []).map((s) => `r/${s}`).join(", ") || "N/A" },
    { label: "News sources", value: String((news.articles || []).length || 0) },
    { label: "Timeline points", value: String((analysis.aggregated_context?.timeline || []).length || 0) },
  ];

  return (
    <div
      className="absolute inset-y-0 right-0 z-40 w-[640px] max-w-[96vw] overflow-y-auto"
      style={{
        background: "linear-gradient(180deg, rgba(13,11,8,0.96) 0%, rgba(10,8,6,0.94) 100%)",
        borderLeft: "1px solid rgba(255,184,0,0.26)",
        boxShadow: "-20px 0 45px rgba(0,0,0,0.45)",
      }}
    >
      <div className="sticky top-0 z-10 px-5 py-3 backdrop-blur-sm" style={{ background: "rgba(10,8,6,0.9)", borderBottom: "1px solid rgba(255,184,0,0.14)" }}>
        <div className="flex items-center justify-between gap-3">
          <button onClick={onBack} className="text-[8px] font-mono uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.45)" }}>
            Back
          </button>
          <button onClick={onClose} className="text-[8px] font-mono uppercase tracking-[0.2em]" style={{ color: "rgba(255,255,255,0.45)" }}>
            Close
          </button>
        </div>
        <h2 className="mt-2 text-[16px] font-mono font-bold leading-snug" style={{ color: "rgba(255,255,255,0.94)" }}>
          {event.title}
        </h2>
      </div>

      <div className="px-5 pb-8">
        <Section title="Executive Summary">
          <div className="space-y-1.5">
            {toBulletLines(analysis.analysis_report).slice(0, 6).map((line, i) => (
              <div key={`${line}-${i}`}>• {line}</div>
            ))}
            {!analysis.analysis_report && <div>No analysis report returned.</div>}
          </div>
        </Section>

        <Section title="Key Facts">
          <div className="grid grid-cols-2 gap-y-1 gap-x-3">
            {keyFacts.map((f) => (
              <div key={f.label} className="contents">
                <div style={{ color: "rgba(255,255,255,0.46)" }}>{f.label}</div>
                <div>{f.value}</div>
              </div>
            ))}
          </div>
        </Section>

        {!!reportSections.length && (
          <Section title="Detailed Analysis">
            <div className="space-y-3">
              {reportSections.slice(0, 8).map((section, i) => (
                <div key={`${section.title}-${i}`}>
                  <div className="text-[9px] uppercase tracking-[0.12em] mb-1" style={{ color: "#FFD54F" }}>
                    {section.title}
                  </div>
                  <div className="space-y-1">
                    {(section.bodyLines.length ? section.bodyLines : ["No additional details."]).slice(0, 6).map((line, j) => (
                      <div key={`${line}-${j}`}>• {line}</div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        <Section title="Timeline">
          {(analysis.aggregated_context?.timeline || []).slice(0, 12).map((t, i) => (
            <div key={`${t}-${i}`}>• {new Date(t).toLocaleString()}</div>
          ))}
        </Section>

        <Section title="Reddit Activity">
          <div>Subreddits: {(reddit.related_subreddits || []).map((s) => `r/${s}`).join(", ") || "N/A"}</div>
          <div className="mt-1">Top posts: {(reddit.top_posts || []).length}</div>
          <div className="mt-2 space-y-1.5">
            {(reddit.top_posts || []).slice(0, 5).map((p) => (
              <div key={p.id}>• {p.title}</div>
            ))}
          </div>
        </Section>

        <Section title="News Coverage">
          <div className="space-y-1.5">
            {(news.articles || []).slice(0, 10).map((a, i) => (
              <a
                key={`${a.url}-${i}`}
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block hover:opacity-80"
                style={{ color: "rgba(255,255,255,0.74)" }}
              >
                • {a.source ? `[${a.source}] ` : ""}{a.title}
              </a>
            ))}
          </div>
        </Section>

        <Section title="Sentiment Analysis">
          <div>Label: {event.sentiment || "neutral"}</div>
          <div>Score: {typeof event.sentiment_score === "number" ? event.sentiment_score.toFixed(2) : "N/A"}</div>
        </Section>

        <Section title="Information Spread">
          <div>
            {(analysis.news_context?.topic_sentences || []).slice(0, 4).map((s, i) => (
              <div key={`${s}-${i}`}>• {s}</div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
