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

const PILLARS = [
  { 
    title: "Global Intelligence (Globe)", 
    desc: "Real-time geopolitical event detection and risk assessment.",
    features: ["9-Layer Processing Pipeline", "LLM-Powered Impact Analysis", "Trust-Verified News Corroboration", "Automated Clustering & Deduplication"]
  },
  { 
    title: "Community Resonance (Polar)", 
    desc: "Analytical mapping of echo chambers and structural isolation.",
    features: ["Echo Score & Lift Metrics", "Interactive Treemap Breakdowns", "Subreddit Media Diet Profiles", "Similarity Cosine Matrix Display"]
  },
  { 
    title: "Narrative Dynamics (Stream)", 
    desc: "Temporal tracking of signal diffusion and z-score spikes.",
    features: ["Z-Score Anomaly Detection", "TF-IDF N-gram Extraction", "5-Cluster Narrative Modeling", "Local DuckDB Persistent Logging"]
  },
  { 
    title: "Structural Modeling (Graph)", 
    desc: "Graph-based visualization of community intersections.",
    features: ["Node-Edge Relationship Mapping", "Narrative Diffusion Paths", "Multi-Dataset Visualization", "Pin-to-Analyze Workflow"]
  },
  { 
    title: "Multi-Agent Research (Crew)", 
    desc: "Autonomous AI agents for deep-dive investigations.",
    features: ["Agentic Research Pipelines", "Cross-Platform Querying", "Synthetic Intelligence Briefs", "Hybrid Search (Vector + SQL)"]
  }
];

export default function OverviewPage() {
  return (
    <div className="min-h-screen flex flex-col bg-[#0a0806] text-[#e6eaf0] font-inter">
      <header className="px-8 py-6 flex items-center justify-between border-b border-white/5 bg-black/40 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-2 bg-gradient-to-r from-[#FFB800] to-[#8B7500] opacity-20 blur-lg animate-pulse" />
            <div className="relative h-12 w-1 bg-[#FFB800]" />
          </div>
          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-[10px] uppercase font-bold tracking-[0.4em] text-[#FFB800] font-mono">
                System.Narrative.Overview
              </span>
              <div className="h-px w-12 bg-[#FFB800]/20" />
              <span className="text-[10px] uppercase font-bold text-white/30 font-mono">v2.4.0 // Global Recon</span>
            </div>
            <h1 className="text-4xl font-black uppercase tracking-tighter leading-none text-white font-manrope">
              Narrative Intelligence Platform
            </h1>
          </div>
        </div>

        <div className="hidden md:flex items-center gap-8 font-mono text-[10px] tracking-widest text-white/40 uppercase" style={{ WebkitFontSmoothing: "antialiased" }}>
          <div className="flex flex-col items-end">
            <span className="text-[#FFB800]/60">Status</span>
            <span className="text-white/80">Operational</span>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-[#FFB800]/60">Nodes</span>
            <span className="text-white/80">Active</span>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-[#FFB800]/60">Integrity</span>
            <span className="text-white/80">Verified</span>
          </div>
        </div>
      </header>

      <main className="flex-1 p-6 grid grid-cols-12 gap-6 max-w-[1600px] mx-auto w-full">
        {/* Main Content Area */}
        <section className="col-span-12 lg:col-span-12 xl:col-span-7 flex flex-col group" style={PANEL}>
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-6 bg-[#FFB800]" style={{ boxShadow: "0 0 15px rgba(255, 184, 0, 0.4)" }} />
              <h2 className="text-[11px] font-black uppercase tracking-[0.2em] text-white/90 font-manrope">Operational Mandate</h2>
            </div>
            <span className="font-mono text-[9px] text-white/20 uppercase tracking-[0.3em]">REF: NSR-2026-ALPHA</span>
          </div>

          <div className="p-8 space-y-6 text-lg leading-relaxed text-white/70 font-inter" style={INNER}>
            <div className="space-y-4">
              <p className="border-l-2 border-[#FFB800]/20 pl-6 py-2 bg-gradient-to-r from-[#FFB800]/[0.02] to-transparent">
                NarrativeSignal is an advanced intelligence framework built to monitor, decode, and visualize the 
                <span className="text-white font-medium italic"> global information environment</span>. It provides a decisive advantage in understanding
                how decentralized digital signals evolve into pervasive societal narratives.
              </p>
              
              <div className="pl-6 space-y-4">
                <p>
                    The platform functions by ingestging millions of data points across social communities, news feeds, and domain metadata. 
                    Unlike traditional monitoring tools that focus on keyword volume, NarrativeSignal focuses on <span className="text-white">structural dynamics</span>: 
                    who is talking to whom, what sources influence them, and where the boundaries of echo chambers are hardening.
                </p>
                <p>
                    By combining <span className="text-white">semantic resolution</span> (understanding the *meaning* of clusters) with 
                    <span className="text-white">propagation tracking</span> (understanding the *spread*), analysts can identify 
                    early-stage narrative "spikes" before they achieve mainstream saturation.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-8 pt-6">
              <div className="p-5 border border-white/5 bg-white/[0.01]">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#FFB800]/80 font-mono mb-3">Intelligence Layer</h3>
                <p className="text-[14px] leading-relaxed">
                  Utilizes custom BERT and LLM architectures to track narrative <span className="text-white">clusters</span>.
                  This enables detection of subtle messaging shifts and strategic intent behind emerging geopolitical events.
                </p>
              </div>
              <div className="p-5 border border-white/5 bg-white/[0.01]">
                <h3 className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#FFB800]/80 font-mono mb-3">Persistence Layer</h3>
                <p className="text-[14px] leading-relaxed">
                  Powered by <span className="text-white italic">DuckDB</span> and high-performance vector stores.
                  All analytical outputs are stored locally for maximum privacy and rapid retrieval during complex correlation tasks.
                </p>
              </div>
            </div>
          </div>
          
          <div className="mt-auto px-6 py-4 border-t border-white/5 bg-white/[0.02] flex justify-between items-center">
            <div className="flex gap-4">
              <div className="h-1 w-8 bg-[#FFB800]/40" />
              <div className="h-1 w-8 bg-white/10" />
              <div className="h-1 w-8 bg-white/10" />
            </div>
            <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.2em]">Authorized Personnel Only</span>
          </div>
        </section>

        {/* Sidebar Capabilities */}
        <aside className="col-span-12 lg:col-span-12 xl:col-span-5 flex flex-col" style={PANEL}>
          <div className="flex items-center gap-3 px-6 py-4 border-b border-white/5">
            <div className="w-1.5 h-6 bg-[#FFB800]" style={{ boxShadow: "0 0 15px rgba(255, 184, 0, 0.4)" }} />
            <h2 className="text-[11px] font-black uppercase tracking-[0.2em] text-white/90 font-manrope">Intelligence Modules & Features</h2>
          </div>

          <div className="p-4 space-y-4 overflow-y-auto custom-scrollbar" style={{ ...INNER, maxHeight: "calc(100vh - 250px)" }}>
            {PILLARS.map((pillar) => (
              <div
                key={pillar.title}
                className="group p-5 border border-white/5 bg-white/[0.02] hover:bg-[#FFB800]/[0.04] hover:border-[#FFB800]/30 transition-all duration-300 relative overflow-hidden"
              >
                <div className="absolute right-0 top-0 w-20 h-20 bg-[#FFB800]/[0.01] rotate-45 translate-x-12 -translate-y-12 group-hover:bg-[#FFB800]/[0.03] transition-colors" />
                
                <div className="flex items-center gap-3 mb-3">
                    <div className="w-1 h-3 bg-[#FFB800]/40 group-hover:bg-[#FFB800] transition-colors" />
                    <h3 className="text-[12px] font-bold uppercase tracking-[0.15em] text-white font-manrope">
                    {pillar.title}
                    </h3>
                </div>
                
                <p className="text-[13px] text-white/50 leading-relaxed mb-4 group-hover:text-white/70 transition-colors">
                  {pillar.desc}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-y-2 gap-x-4">
                    {pillar.features.map((feat, idx) => (
                        <div key={idx} className="flex items-start gap-2">
                            <span className="text-[#FFB800] font-mono text-[9px] mt-1">▸</span>
                            <span className="text-[10px] uppercase font-bold tracking-wider text-white/30 group-hover:text-white/60 transition-colors">
                                {feat}
                            </span>
                        </div>
                    ))}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-auto p-6 bg-gradient-to-t from-[#FFB800]/[0.03] to-transparent">
            <div className="p-4 border border-[#FFB800]/20 bg-black/40 rounded-sm">
                <div className="flex items-center gap-2 mb-2">
                    <div className="w-2 h-2 rounded-full bg-[#FFB800] animate-pulse" />
                    <span className="text-[9px] font-mono text-[#FFB800] uppercase tracking-widest">System Alert</span>
                </div>
                <p className="text-[11px] text-white/40 leading-snug">
                    New narrative detected in Central European clusters. Corroborating with local news feeds.
                </p>
            </div>
          </div>
        </aside>
      </main>
      
      {/* Decorative footer footer */}
      <footer className="p-4 border-t border-white/5 flex justify-between items-center bg-black/20">
        <div className="flex gap-12 font-mono text-[9px] text-white/20 uppercase tracking-[0.4em]">
            <span>Sec-Scan: Clean</span>
            <span>Uptime: 99.98%</span>
            <span>Latency: 42ms</span>
        </div>
        <div className="w-32 h-1 bg-gradient-to-r from-transparent via-[#FFB800]/20 to-transparent" />
      </footer>
    </div>
  );
}
