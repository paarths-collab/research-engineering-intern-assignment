const PANEL = {
  background: "rgba(10, 8, 6, 0.48)",
  backdropFilter: "blur(20px)",
  border: "1px solid rgba(255, 184, 0, 0.10)",
};

const WORKFLOW = [
  {
    title: "1. Detect the event",
    desc: "Bring together open-web news and public discussion around the same real-world event.",
    detail: "GDELT + news/RSS first; social connectors plug into the same pipeline."
  },
  {
    title: "2. Extract narratives",
    desc: "Cluster competing interpretations, claims and frames instead of only counting keywords.",
    detail: "Every narrative keeps links back to the underlying evidence."
  },
  {
    title: "3. Track propagation",
    desc: "Measure when a narrative appears, spikes and moves between sources or communities.",
    detail: "Timeline + graph views make the spread inspectable."
  },
  {
    title: "4. Investigate evidence",
    desc: "Ask questions about an event and trace every answer back to source material.",
    detail: "The goal is analyst acceleration, not a black-box verdict."
  }
];

const SOURCES = [
  ["GDELT", "Event + news discovery", "Core"],
  ["News / RSS", "Original reporting and official sources", "Core"],
  ["Bluesky", "Public social discussion", "Connector"],
  ["Threads", "Public keyword-search discussion", "Connector"],
  ["Hacker News", "Tech / AI / business discussion", "Connector"],
];

export default function OverviewPage() {
  return (
    <div className="min-h-screen bg-[#0a0806] text-[#e6eaf0] px-6 py-8 lg:px-10">
      <main className="max-w-[1400px] mx-auto space-y-6">
        <section className="pt-10 pb-4">
          <div className="text-[10px] uppercase font-bold tracking-[0.35em] text-[#FFB800] font-mono mb-4">
            NarrativeSignal / V1
          </div>
          <h1 className="text-4xl md:text-6xl font-black tracking-tight text-white max-w-5xl leading-[0.98]">
            Understand how real-world events become online narratives.
          </h1>
          <p className="mt-6 text-base md:text-xl text-white/55 max-w-3xl leading-relaxed">
            NarrativeSignal is an early open-web intelligence prototype for discovering events, identifying competing narratives, tracking how they spread, and inspecting the evidence behind the analysis.
          </p>
          <div className="mt-7 flex flex-wrap gap-3 text-[11px] uppercase tracking-wider font-mono">
            <span className="px-3 py-2 border border-[#FFB800]/30 text-[#FFB800]">Early prototype</span>
            <span className="px-3 py-2 border border-white/10 text-white/45">Open-web data</span>
            <span className="px-3 py-2 border border-white/10 text-white/45">Evidence-first</span>
          </div>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {WORKFLOW.map((item) => (
            <article key={item.title} className="p-6 lg:p-7" style={PANEL}>
              <h2 className="text-sm font-black uppercase tracking-[0.14em] text-white mb-3">{item.title}</h2>
              <p className="text-white/65 leading-relaxed mb-4">{item.desc}</p>
              <p className="text-xs font-mono text-[#FFB800]/65 leading-relaxed">{item.detail}</p>
            </article>
          ))}
        </section>

        <section className="grid grid-cols-1 xl:grid-cols-3 gap-5">
          <div className="xl:col-span-2 p-6 lg:p-8" style={PANEL}>
            <div className="flex items-center justify-between gap-4 mb-6">
              <div>
                <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#FFB800] mb-2">Data layer</div>
                <h2 className="text-2xl font-black text-white">One normalized pipeline</h2>
              </div>
              <span className="text-[10px] uppercase tracking-widest text-white/30 font-mono">source-agnostic</span>
            </div>

            <div className="space-y-2">
              {SOURCES.map(([name, use, status]) => (
                <div key={name} className="grid grid-cols-[110px_1fr_auto] gap-4 items-center px-4 py-3 border border-white/5 bg-black/20">
                  <span className="font-bold text-white text-sm">{name}</span>
                  <span className="text-sm text-white/45">{use}</span>
                  <span className="text-[9px] font-mono uppercase tracking-wider text-[#FFB800]/70">{status}</span>
                </div>
              ))}
            </div>

            <div className="mt-6 px-4 py-4 border border-[#FFB800]/10 bg-[#FFB800]/[0.025] font-mono text-xs text-white/45 leading-relaxed">
              source connector → raw store → normalization → event matching → narrative clustering → propagation → evidence
            </div>
          </div>

          <aside className="p-6 lg:p-8" style={PANEL}>
            <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#FFB800] mb-2">Who this V1 is for</div>
            <h2 className="text-2xl font-black text-white mb-6">Research users first</h2>
            <div className="space-y-4 text-sm text-white/60 leading-relaxed">
              <p><span className="text-white font-semibold">OSINT analysts</span> — follow emerging claims and source trails.</p>
              <p><span className="text-white font-semibold">Journalists</span> — compare how an event is being framed and find primary evidence.</p>
              <p><span className="text-white font-semibold">Disinformation researchers</span> — inspect narrative emergence, amplification and cross-community movement.</p>
              <p><span className="text-white font-semibold">Geopolitical / risk teams</span> — rapidly orient around developing events.</p>
            </div>
          </aside>
        </section>

        <section className="p-6 lg:p-8 border border-white/5 bg-black/25">
          <div className="text-[10px] font-mono uppercase tracking-[0.3em] text-[#FFB800] mb-3">What we are testing</div>
          <p className="text-lg text-white/70 max-w-4xl leading-relaxed">
            Not whether the dashboard looks impressive. We are testing whether analysts can get from <span className="text-white">a developing event → the important narratives → their spread → the source evidence</span> faster than they can today.
          </p>
        </section>
      </main>
    </div>
  );
}
