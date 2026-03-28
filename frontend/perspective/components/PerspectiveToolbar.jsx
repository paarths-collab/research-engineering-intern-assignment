"use client";

import { useEffect, useRef, useState } from 'react';
import useGraphStore from '../store/graphStore';
import {
  fetchNewsPresets,
  fetchPersonaPresets,
  getCachedNewsPresets,
  getFallbackPersonaPresets,
  simulateGraph,
} from '../services/perspectiveAPI';

export default function PerspectiveToolbar({ onAddPersona, onAddNews, onAddDiscussion, onAddDebate }) {
  const { nodes, edges, debateRounds, setDebateRounds, resetGraph, deleteSelectedNodes, isSimulating, setSimulating, applySimulationResult } = useGraphStore();
  const selectedCount = nodes.filter((n) => n.selected).length;
  const [openMenu, setOpenMenu] = useState(null);
  const [personaPresets, setPersonaPresets] = useState(() => getFallbackPersonaPresets());
  const [newsPresets, setNewsPresets] = useState([]);
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
    fetchPersonaPresets()
      .then((items) => {
        if (!cancelled && Array.isArray(items) && items.length > 0) {
          setPersonaPresets(items);
        }
      })
      .catch((error) => {
        console.error('Failed to load persona presets', error);
        if (!cancelled) setPersonaPresets(getFallbackPersonaPresets());
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    // Hydrate cached headlines after mount to keep SSR/CSR initial HTML identical.
    const cached = getCachedNewsPresets();
    if (cached.length > 0) {
      setNewsPresets(cached);
    }

    let cancelled = false;
    fetchNewsPresets(20)
      .then((items) => {
        if (!cancelled) setNewsPresets(items);
      })
      .catch((error) => {
        console.error('Failed to load globe news presets', error);
        if (!cancelled) setNewsPresets(getCachedNewsPresets());
      });

    return () => {
      cancelled = true;
    };
  }, []);

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
      alert(
        'Valid flows:\n1) Normal: at least 1 Persona -> 1 News\n2) Debate/Discussion: at least 2 Personas -> Discussion/Debate -> News'
      );
      return;
    }
    setSimulating(true);
    try {
      const result = await simulateGraph(nodes, edges, { debateRounds });
      applySimulationResult(result);
    } catch (e) {
      console.error(e);
      alert('Simulation failed. Make sure the backend is running.');
      setSimulating(false);
    }
  };

  return (
    <div className="perspective-toolbar" ref={toolbarRef}>
      <div className="toolbar-brand">
        <span className="brand-dot" />
        <span className="brand-name">Perspective</span>
      </div>

      <div className="toolbar-section">
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
              Persona Presets
            </button>
            <div className="preset-dropdown">
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
              suppressHydrationWarning
            >
              News Presets
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
                  Loading headlines...
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
    </div>
  );
}
