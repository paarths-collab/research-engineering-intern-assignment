"use client";

import PerspectiveCanvas from './components/PerspectiveCanvas';

export default function PerspectivePage() {
  return (
    <div className="perspective-page-shell">
      <header className="perspective-page-header">
        <div className="perspective-header-left">
          <div className="perspective-header-bar-wrap">
            <div className="perspective-header-bar-glow" />
            <div className="perspective-header-bar" />
          </div>
          <div>
            <div className="perspective-header-meta-row">
              <span className="perspective-header-meta">System.Narrative.Perspective</span>
              <div className="perspective-header-line" />
              <div className="perspective-header-live">
                <span className="live-dot" />
                <span className="live-label">Real-time Stream Active</span>
              </div>
            </div>
            <h1 className="perspective-header-title">Perspective Ecosystem Intelligence</h1>
          </div>
        </div>
      </header>

      <main className="perspective-page-main">
        <PerspectiveCanvas />
      </main>
    </div>
  );
}
