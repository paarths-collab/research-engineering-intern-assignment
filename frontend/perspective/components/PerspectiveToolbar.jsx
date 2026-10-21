"use client";

import { useEffect, useRef, useState } from 'react';
import useGraphStore from '../store/graphStore';
import {
  getCachedNewsPresets,
  getFallbackPersonaPresets,
  loadNewsPresets,
  loadPersonaPresets,
  simulateGraph,
} from '../services/perspectiveAPI';

export default function PerspectiveToolbar({ onAddPersona, onAddNews, onAddDiscussion, onAddDebate }) {
  const { nodes, edges, debateRounds, setDebateRounds, resetGraph, deleteSelectedNodes, isSimulating, setSimulating, applySimulationResult } = useGraphStore();
  const selectedCount = nodes.filter((n) => n.selected).length;
  const [openMenu, setOpenMenu] = useState(null);
  const [personaPresets, setPersonaPresets] = useState(() => getFallbackPersonaPresets());
  const [newsPresets, setNewsPresets] = useState([]);
  // 'loading' | 'ready' | 'unavailable' for each preset list; the persona list always has a built-in fallback.
  const [personaStatus, setPersonaStatus] = useState('loading');
  const [newsStatus, setNewsStatus] = useState('loading');
  const [presetReloadKey, setPresetReloadKey] = useState(0);
  const [message, setMessage] = useState(null);
  const toolbarRef = useRef(null);

  useEffect(() => {
    const onPointerDown = (event) => {
      if (!toolbarRef.current?.contains(event.target)) {
        setOpenMenu(null);
      }
    };

    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setPersonaStatus('loading');
    loadPersonaPresets()
      .then(({ items, source }) => {
        if (cancelled) return;
        if (Array.isArray(items) && items.length > 0) setPersonaPresets(items);
        setPersonaStatus(source === 'live' ? 'ready' : 'unavailable');
      })
      .catch((error) => {
        console.error('Failed to load persona presets', error);
        if (cancelled) return;
        setPersonaPresets(getFallbackPersonaPresets());
        setPersonaStatus('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [presetReloadKey]);

  useEffect(() => {
    // Hydrate cached headlines after mount to keep SSR/CSR initial HTML identical.
    const cached = getCachedNewsPresets();
    if (cached.length > 0) {
      setNewsPresets(cached);
    }

    let cancelled = false;
    setNewsStatus('loading');
    loadNewsPresets(20)
      .then(({ items, source }) => {
        if (cancelled) return;
        setNewsPresets(items);
        setNewsStatus(source === 'live' ? 'ready' : source === 'empty' ? 'empty' : 'unavailable');
      })
      .catch((error) => {
        console.error('Failed to load globe news presets', error);
        if (cancelled) return;
        setNewsPresets(getCachedNewsPresets());
        setNewsStatus('unavailable');
      });

    return () => {
      cancelled = true;
    };
  }, [presetReloadKey]);

  const presetsLoading = personaStatus === 'loading' || newsStatus === 'loading';
  const presetsUnavailable = !presetsLoading && (personaStatus === 'unavailable' || newsStatus === 'unavailable' || newsStatus === 'empty');
  const retryPresets = () => {
    setMessage(null);
    setPresetReloadKey((k) => k + 1);
  };

  const handleSimulate = async () => {
    const personas = nodes.filter(n => n.type === 'persona');
    const news = nodes.filter(n => n.type === 'news');
    const connectors = nodes.filter((n) => n.type === 'discussion' || n.type === 'debate');
    const nodeById = new Map(nodes.map((n) => [n.id, n]));
    const personaToConnectorCount = new Map();
    const connectorToNews = new Set();
    let hasDirectPersonaToNews = false;

    edges.forEach((e) => {
      const source = nodeById.get(e.source);
      const target = nodeById.get(e.target);
      if (!source || !target) return;

      if (
        (source.type === 'persona' && target.type === 'news') ||
        (source.type === 'news' && target.type === 'persona')
      ) {
        hasDirectPersonaToNews = true;
      }

      if (
        source.type === 'persona' &&
        (target.type === 'discussion' || target.type === 'debate')
      ) {
        personaToConnectorCount.set(target.id, (personaToConnectorCount.get(target.id) || 0) + 1);
      } else if (
        target.type === 'persona' &&
        (source.type === 'discussion' || source.type === 'debate')
      ) {
        personaToConnectorCount.set(source.id, (personaToConnectorCount.get(source.id) || 0) + 1);
      }

      if (
        (source.type === 'discussion' || source.type === 'debate') && target.type === 'news'
      ) {
        connectorToNews.add(source.id);
      } else if (
        (target.type === 'discussion' || target.type === 'debate') && source.type === 'news'
      ) {
        connectorToNews.add(target.id);
      }
    });

    const hasValidNormalFlow = personas.length >= 1 && news.length >= 1 && hasDirectPersonaToNews;
    const hasValidDebateDiscussionFlow = connectors.length >= 1 && Array.from(personaToConnectorCount.entries()).some(
      ([connectorId, personaCount]) => connectorToNews.has(connectorId) && personaCount >= 2
    );

    if (!hasValidNormalFlow && !hasValidDebateDiscussionFlow) {
      setMessage({
        kind: 'warn',
        text: 'Connect your nodes first. Valid flows: 1) Normal: at least 1 Persona -> 1 News. 2) Debate/Discussion: at least 2 Personas -> Discussion/Debate -> News.',
      });
      return;
    }
    setMessage(null);
    setSimulating(true);
    try {
      const result = await simulateGraph(nodes, edges, { debateRounds });
      applySimulationResult(result);
    } catch (e) {
      console.error(e);
      setMessage({
        kind: 'error',
        text: 'Simulation failed: the backend is unreachable or did not respond in time. If it was idle, the first request can take about 30 seconds to wake up. Wait a moment and press Simulate again.',
      });
      setSimulating(false);
    }
  };

  return (
    <div className="perspective-toolbar" ref={toolbarRef}>
      <div className="toolbar-brand">
        <span className="brand-dot" />
        <span className="brand-name">Perspective</span>
      </div>

      <div className="toolbar-section toolbar-section-wrap">
        <div className="toolbar-label">Add Node</div>
        <div className="toolbar-buttons">
          <div className={`preset-group ${openMenu === 'persona' ? 'open' : ''}`}>
            <button
              className="toolbar-btn persona-btn"
              onClick={() => {
                if (personaPresets.length === 0) {
                  onAddPersona(null);
                  setOpenMenu(null);
                  return;
                }
                setOpenMenu((m) => (m === 'persona' ? null : 'persona'));
              }}
              suppressHydrationWarning
            >
              {personaStatus === 'loading' ? 'Persona Presets (loading…)' : 'Persona Presets'}
            </button>
            <div className="preset-dropdown">
              {personaStatus === 'loading' && (
                <div className="preset-note">Loading live presets… showing the built-in list meanwhile.</div>
              )}
              {personaStatus === 'unavailable' && (
                <div className="preset-note preset-note-warn">Backend unreachable: showing built-in or cached presets.</div>
              )}
              {personaPresets.map((p, i) => (
                <button
                  key={i}
                  className="preset-item"
                  onClick={() => {
                    onAddPersona(p);
                    setOpenMenu(null);
                  }}
                  title={p.description || p.label}
                  suppressHydrationWarning
                >
                  {p.label}
                </button>
              ))}
              {personaPresets.length === 0 && (
                <div className="preset-item" style={{ cursor: 'default', opacity: 0.7 }}>
                  Presets unavailable. Click Persona Presets to add a manual persona.
                </div>
              )}
            </div>
          </div>
          <div className={`preset-group ${openMenu === 'news' ? 'open' : ''}`}>
            <button
              className="toolbar-btn news-btn"
              onClick={() => setOpenMenu((m) => (m === 'news' ? null : 'news'))}
              disabled={newsPresets.length === 0}
              title={
                newsStatus === 'loading' && newsPresets.length === 0
                  ? 'Loading headlines from the backend. This can take up to ~30s after a cold start.'
                  : newsPresets.length === 0
                    ? 'No headlines available. Use Retry.'
                    : undefined
              }
              suppressHydrationWarning
            >
              {newsStatus === 'loading' && newsPresets.length === 0
                ? 'Loading presets…'
                : newsStatus !== 'ready' && newsPresets.length === 0
                  ? 'News unavailable'
                  : 'News Presets'}
            </button>
            <div className="preset-dropdown">
              {newsPresets.map((n, i) => (
                <button
                  key={i}
                  className="preset-item"
                  onClick={() => {
                    onAddNews(n);
                    setOpenMenu(null);
                  }}
                  suppressHydrationWarning
                >
                  {n.label}
                </button>
              ))}
              {newsPresets.length === 0 && (
                <div className="preset-item" style={{ cursor: 'default', opacity: 0.7 }}>
                  {newsStatus === 'loading' ? 'Loading headlines…' : 'No headlines available.'}
                </div>
              )}
            </div>
          </div>
          <button
            className="toolbar-btn discussion-btn"
            onClick={onAddDiscussion}
            title="Add discussion node"
            suppressHydrationWarning
          >
            Discussion Node
          </button>
          <button
            className="toolbar-btn debate-btn"
            onClick={onAddDebate}
            title="Add debate node"
            suppressHydrationWarning
          >
            Debate Node
          </button>
        </div>
        {(presetsLoading || presetsUnavailable) && (
          <div className={`preset-status ${presetsUnavailable ? 'preset-status-warn' : ''}`} role="status">
            {presetsLoading ? (
              <>
                <span className="spinner spinner-small" />
                <span>Loading presets… the first request can take up to ~30s.</span>
              </>
            ) : (
              <>
                <span>
                  {newsStatus === 'empty' && personaStatus !== 'unavailable'
                    ? 'The backend returned no news headlines.'
                    : newsPresets.length === 0
                      ? 'Backend unreachable: no news headlines loaded.'
                      : 'Backend unreachable: showing cached presets.'}
                </span>
                <button type="button" className="preset-retry-btn" onClick={retryPresets} suppressHydrationWarning>
                  Retry
                </button>
              </>
            )}
          </div>
        )}
      </div>

      <div className="toolbar-divider" />

      <div className="toolbar-section rounds-section">
        <span className="toolbar-label">Debate Rounds</span>
        <input
          type="number"
          min={1}
          max={20}
          value={debateRounds}
          onChange={(e) => setDebateRounds(e.target.value)}
          className="rounds-input"
          suppressHydrationWarning
        />
      </div>

      <div className="toolbar-divider" />

      <div className="toolbar-section">
        <button
          className={`simulate-btn ${isSimulating ? 'simulating' : ''}`}
          onClick={handleSimulate}
          disabled={isSimulating}
          suppressHydrationWarning
        >
          {isSimulating ? (
            <><span className="spinner" /> Analyzing...</>
          ) : (
            <><span className="play-icon">▶</span> Simulate</>
          )}
        </button>
        <button
          className="delete-btn"
          onClick={deleteSelectedNodes}
          disabled={selectedCount === 0}
          title="Delete selected nodes"
          suppressHydrationWarning
        >
          Delete Selected
        </button>
        <button className="reset-btn" onClick={resetGraph} suppressHydrationWarning>Reset</button>
      </div>

      {(message || isSimulating) && (
        <div
          className={`toolbar-notice toolbar-notice-${isSimulating ? 'info' : message.kind}`}
          role={!isSimulating && message.kind === 'error' ? 'alert' : 'status'}
        >
          <span>
            {isSimulating
              ? 'Contacting the backend… the first request after idle can take up to ~30s.'
              : message.text}
          </span>
          {!isSimulating && (
            <button
              type="button"
              className="toolbar-notice-close"
              onClick={() => setMessage(null)}
              aria-label="Dismiss message"
              suppressHydrationWarning
            >
              ×
            </button>
          )}
        </div>
      )}
    </div>
  );
}
