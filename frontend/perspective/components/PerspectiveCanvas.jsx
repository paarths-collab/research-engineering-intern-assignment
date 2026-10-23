"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background, MiniMap, Controls,
  ReactFlowProvider, BackgroundVariant,
  useReactFlow, useStoreApi
} from 'reactflow';
import 'reactflow/dist/style.css';

import useGraphStore from '../store/graphStore';
import PersonaNode from '../nodes/PersonaNode';
import NewsNode from '../nodes/NewsNode';
import DiscussionNode from '../nodes/DiscussionNode';
import DebateNode from '../nodes/DebateNode';
import AnalysisNode from '../nodes/AnalysisNode';
import PerspectiveToolbar from './PerspectiveToolbar';
import { SimulationBadge, GenerationTag, summarizeGeneration } from '../nodes/SimulationBadge';
import '../styles/canvas.css';
import '../styles/nodes.css';

const nodeTypes = {
  persona: PersonaNode,
  news: NewsNode,
  discussion: DiscussionNode,
  debate: DebateNode,
  analysis: AnalysisNode,
};

const generateNodeId = (existingNodes) => {
  const used = new Set(existingNodes.map((n) => n.id));
  // Fast Refresh can reset module state; use random/time-based IDs and check collisions.
  for (let i = 0; i < 5; i += 1) {
    const candidate = `node-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    if (!used.has(candidate)) return candidate;
  }

  let suffix = 1;
  let fallback = `node-${Date.now().toString(36)}-${suffix}`;
  while (used.has(fallback)) {
    suffix += 1;
    fallback = `node-${Date.now().toString(36)}-${suffix}`;
  }
  return fallback;
};

// ---------------------------------------------------------------------------
// Connection rules (mirrors the Simulate validator in PerspectiveToolbar.jsx):
//   Persona -> News, Persona -> Discussion/Debate, Discussion/Debate -> News.
// ---------------------------------------------------------------------------
const CONNECTOR_TYPES = new Set(['discussion', 'debate']);
const VALID_FLOWS_MESSAGE =
  'Valid connections: Persona -> News, Persona -> Discussion/Debate, Discussion/Debate -> News.';

const getConnectionIssue = (connection, nodes, edges) => {
  if (!connection?.source || !connection?.target) return 'Drop on a connection handle (the circles on a node).';
  if (connection.source === connection.target) return `A node cannot connect to itself. ${VALID_FLOWS_MESSAGE}`;

  const source = nodes.find((n) => n.id === connection.source);
  const target = nodes.find((n) => n.id === connection.target);
  if (!source || !target) return VALID_FLOWS_MESSAGE;

  const allowed =
    (source.type === 'persona' && (target.type === 'news' || CONNECTOR_TYPES.has(target.type))) ||
    (CONNECTOR_TYPES.has(source.type) && target.type === 'news');
  if (!allowed) return `Cannot connect ${source.type} to ${target.type}. ${VALID_FLOWS_MESSAGE}`;

  const duplicate = edges.some((e) => e.source === connection.source && e.target === connection.target);
  if (duplicate) return 'These two nodes are already connected.';

  return null;
};

// ---------------------------------------------------------------------------
// Placement of newly added nodes inside the currently visible viewport.
// ---------------------------------------------------------------------------
const DEFAULT_NODE_SIZE = { width: 220, height: 150 };
const PLACEMENT_GAP = 28;

// Small per-type offsets (flow units) from the visible centre so types fan out naturally:
// personas upper-left, connectors in the middle, news lower-right.
const TYPE_OFFSETS = {
  persona: { x: -300, y: -170 },
  discussion: { x: -60, y: -40 },
  debate: { x: 180, y: -40 },
  news: { x: -60, y: 110 },
};

const rectsOverlap = (a, b, gap) =>
  a.x < b.x + b.width + gap
  && a.x + a.width + gap > b.x
  && a.y < b.y + b.height + gap
  && a.y + a.height + gap > b.y;

const findFreePosition = (start, existingNodes, size = DEFAULT_NODE_SIZE) => {
  const rects = existingNodes.map((n) => ({
    x: n.position?.x ?? 0,
    y: n.position?.y ?? 0,
    width: n.width || DEFAULT_NODE_SIZE.width,
    height: n.height || DEFAULT_NODE_SIZE.height,
  }));

  // Candidate grid cells ordered by distance from the preferred spot.
  const stepX = size.width + PLACEMENT_GAP;
  const stepY = size.height + PLACEMENT_GAP;
  const cells = [];
  for (let i = -5; i <= 5; i += 1) {
    for (let j = -4; j <= 4; j += 1) cells.push([i, j]);
  }
  cells.sort((a, b) => (a[0] ** 2 + a[1] ** 2) - (b[0] ** 2 + b[1] ** 2) || b[1] - a[1] || a[0] - b[0]);

  for (const [i, j] of cells) {
    const candidate = { x: start.x + i * stepX, y: start.y + j * stepY, width: size.width, height: size.height };
    if (!rects.some((r) => rectsOverlap(candidate, r, PLACEMENT_GAP / 2))) {
      return { x: Math.round(candidate.x), y: Math.round(candidate.y) };
    }
  }
  return { x: Math.round(start.x), y: Math.round(start.y) };
};

const FIT_VIEW_OPTIONS = { padding: 0.3, duration: 300, maxZoom: 1.1 };
const MINIMAP_MIN_PANE_WIDTH = 900;
const FIT_PENDING_MS = 4000;
const NOTICE_MS = 6000;
const TOAST_MS = 20000;

function Canvas() {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, deleteSelectedNodes, focusNode, simulationResult } = useGraphStore();
  const reactFlowWrapper = useRef(null);
  const flowPaneRef = useRef(null);
  const rfInstance = useRef(null);
  const storeApi = useStoreApi();
  const { screenToFlowPosition, fitView } = useReactFlow();
  const pendingFitRef = useRef(0);
  const [paneWidth, setPaneWidth] = useState(0);
  const [notice, setNotice] = useState(null);
  const noticeTimerRef = useRef(null);
  const [toastDismissed, setToastDismissed] = useState(false);
  const [collapsedSections, setCollapsedSections] = useState({
    persona: true,
    news: true,
    discussion: true,
    debate: true,
  });

  const [panelCollapsed, setPanelCollapsed] = useState(false);
  // The minimap sits over the node area, so only show it when the canvas is wide enough.
  const showMiniMap = paneWidth >= MINIMAP_MIN_PANE_WIDTH;

  useEffect(() => {
    const onKeyDown = (event) => {
      const tag = event.target?.tagName;
      const isTypingTarget = tag === 'INPUT' || tag === 'TEXTAREA' || event.target?.isContentEditable;
      if (isTypingTarget) return;

      if (event.key === 'Delete' || event.key === 'Backspace') {
        deleteSelectedNodes();
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [deleteSelectedNodes]);

  // --- viewport / overlay helpers -----------------------------------------
  useEffect(() => {
    const el = flowPaneRef.current;
    if (!el) return undefined;
    setPaneWidth(el.getBoundingClientRect().width);
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect?.width;
      if (typeof width === 'number') setPaneWidth(width);
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => () => clearTimeout(noticeTimerRef.current), []);

  const showNotice = useCallback((text) => {
    clearTimeout(noticeTimerRef.current);
    setNotice({ id: Date.now(), text });
    noticeTimerRef.current = setTimeout(() => setNotice(null), NOTICE_MS);
  }, []);

  // Reset the dismissed state whenever a new simulation result arrives, and auto-hide it later.
  useEffect(() => {
    setToastDismissed(false);
    if (!simulationResult) return undefined;
    const timer = setTimeout(() => setToastDismissed(true), TOAST_MS);
    return () => clearTimeout(timer);
  }, [simulationResult]);

  // Frame everything (including a node that was just added) once the new node has been measured.
  // pendingFitRef holds an expiry timestamp so a late, unrelated node change never triggers a surprise re-fit.
  const requestFit = useCallback(() => {
    pendingFitRef.current = Date.now() + FIT_PENDING_MS;
  }, []);

  useEffect(() => {
    if (!pendingFitRef.current) return;
    if (Date.now() > pendingFitRef.current) {
      pendingFitRef.current = 0;
      return;
    }
    if (nodes.length === 0 || !nodes.every((n) => n.width && n.height)) return;
    pendingFitRef.current = 0;
    fitView(FIT_VIEW_OPTIONS);
  }, [nodes, fitView]);

  // Preferred spot for a new node: the centre of the visible canvas, offset a little per node type.
  const getPlacement = useCallback((type) => {
    const rect = flowPaneRef.current?.getBoundingClientRect();
    const centre = rect && rect.width > 0 && rect.height > 0
      ? screenToFlowPosition({ x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 })
      : { x: 400, y: 250 };
    const offset = TYPE_OFFSETS[type] || { x: 0, y: 0 };
    const start = { x: centre.x + offset.x, y: centre.y + offset.y };
    return findFreePosition(start, useGraphStore.getState().nodes);
  }, [screenToFlowPosition]);

  const handleAddPersona = useCallback((preset) => {
    const id = generateNodeId(nodes);
    const count = nodes.filter(n => n.type === 'persona').length;
    const safePreset = preset || {
      label: `Persona ${count + 1}`,
      description: 'Manually created persona. Edit traits and connect to discussion/debate, then to news.',
      traits: ['generalist', 'observer'],
      ideology_vector: [0.5, 0.5, 0.5, 0.5],
    };

    addNode({
      id,
      type: 'persona',
      position: getPlacement('persona'),
      data: safePreset
    });
    requestFit();
  }, [nodes, addNode, getPlacement, requestFit]);

  const handleAddNews = useCallback((preset) => {
    if (!preset) return;

    const id = generateNodeId(nodes);
    addNode({
      id,
      type: 'news',
      position: getPlacement('news'),
      data: preset
    });
    requestFit();
  }, [nodes, addNode, getPlacement, requestFit]);

  const handleAddDiscussion = useCallback(() => {
    const id = generateNodeId(nodes);
    addNode({
      id,
      type: 'discussion',
      position: getPlacement('discussion'),
      data: {
        label: 'Discussion'
      }
    });
    requestFit();
  }, [nodes, addNode, getPlacement, requestFit]);

  const handleAddDebate = useCallback(() => {
    const id = generateNodeId(nodes);
    addNode({
      id,
      type: 'debate',
      position: getPlacement('debate'),
      data: {
        label: 'Debate'
      }
    });
    requestFit();
  }, [nodes, addNode, getPlacement, requestFit]);

  // --- connection validation -----------------------------------------------
  const isValidConnection = useCallback((connection) => {
    const state = useGraphStore.getState();
    return getConnectionIssue(connection, state.nodes, state.edges) === null;
  }, []);

  // React Flow keeps connectionStatus / start / end handles in its store until after onConnectEnd runs,
  // so a drop that was rejected can be explained here without extra bookkeeping.
  const onConnectEnd = useCallback(() => {
    const { connectionStatus, connectionStartHandle, connectionEndHandle } = storeApi.getState();
    if (connectionStatus !== 'invalid') return;

    if (!connectionStartHandle || !connectionEndHandle) {
      showNotice(`Connect from an output handle to an input handle. ${VALID_FLOWS_MESSAGE}`);
      return;
    }

    const fromSource = connectionStartHandle.type === 'source';
    const connection = fromSource
      ? { source: connectionStartHandle.nodeId, target: connectionEndHandle.nodeId }
      : { source: connectionEndHandle.nodeId, target: connectionStartHandle.nodeId };
    const state = useGraphStore.getState();
    showNotice(getConnectionIssue(connection, state.nodes, state.edges) || VALID_FLOWS_MESSAGE);
  }, [storeApi, showNotice]);

  const onContextMenu = useCallback((event) => {
    event.preventDefault();
  }, []);

  const groupedNodes = useMemo(() => {
    const byType = {
      persona: nodes.filter((n) => n.type === 'persona'),
      news: nodes.filter((n) => n.type === 'news'),
      analysis: nodes.filter((n) => n.type === 'analysis'),
      discussion: nodes.filter((n) => n.type === 'discussion'),
      debate: nodes.filter((n) => n.type === 'debate'),
    };
    return byType;
  }, [nodes]);

  const analysisEntries = useMemo(() => {
    if (!simulationResult) {
      return [];
    }

    const entries = [];

    if (simulationResult?.summary) {
      entries.push({
        id: 'simulation-summary',
        nodeId: null,
        type: 'analysis',
        title: 'Simulation Summary',
        text: simulationResult.summary,
        simulated: Boolean(simulationResult.simulated),
        generationSummary: summarizeGeneration(simulationResult.generation),
      });
    }

    for (const node of nodes) {
      if (!['news', 'analysis', 'discussion', 'debate'].includes(node.type)) continue;

      const text = node.data?.analysis_summary || node.data?.summary || node.data?.description || '';
      if (!text) continue;

      entries.push({
        id: `analysis-${node.id}`,
        nodeId: node.id,
        type: node.type,
        title: node.data?.label || node.type,
        text,
        simulated: Boolean(node.data?.simulated),
        generationSummary: summarizeGeneration(node.data?.generation),
      });

      const reactions = Array.isArray(node.data?.reactions) ? node.data.reactions : [];
      for (const [idx, reaction] of reactions.entries()) {
        if (!reaction?.reaction) continue;
        entries.push({
          id: `analysis-reaction-${node.id}-${idx}`,
          nodeId: node.id,
          type: node.type,
          title: `${reaction.persona || 'Persona'} reaction`,
          text: reaction.reaction,
          generation: reaction,
        });
      }
    }

    return entries;
  }, [nodes, simulationResult]);

  const handlePanelCardClick = (nodeId) => {
    const target = nodes.find((n) => n.id === nodeId);
    if (!target) return;

    focusNode(nodeId);
    if (rfInstance.current?.setCenter) {
      rfInstance.current.setCenter(target.position.x, target.position.y, { zoom: 1.05, duration: 350 });
    }
  };

  const toggleSection = (type) => {
    setCollapsedSections((prev) => ({ ...prev, [type]: !prev[type] }));
  };

  const renderNodeStack = (type, label) => {
    const items = groupedNodes[type] || [];
    const shouldCollapse = items.length > 4;
    const showAll = !collapsedSections[type];
    const visible = shouldCollapse && !showAll ? items.slice(0, 4) : items;

    return (
      <section className="side-section" key={type}>
        <div className="side-section-head">
          <div className="side-section-title-wrap">
            <span className={`side-dot side-dot-${type}`} />
            <span className="side-section-title">{label}</span>
          </div>
          <span className="side-section-count">{items.length}</span>
        </div>

        {items.length === 0 ? (
          <div className="side-empty">No {label.toLowerCase()} yet</div>
        ) : (
          <div className="side-stack">
            {visible.map((node) => (
              <button
                type="button"
                className={`side-card side-card-${type} ${node.selected ? 'active' : ''}`}
                key={node.id}
                onClick={() => handlePanelCardClick(node.id)}
              >
                <div className="side-card-title">{node.data?.label || node.id}</div>
                {node.data?.description && <div className="side-card-sub">{node.data.description}</div>}
              </button>
            ))}
          </div>
        )}

        {shouldCollapse && (
          <button className="side-toggle" onClick={() => toggleSection(type)}>
            {showAll ? 'Collapse' : `Show all ${items.length}`}
          </button>
        )}
      </section>
    );
  };

  return (
    <div className="perspective-layout">
      <PerspectiveToolbar
        onAddPersona={handleAddPersona}
        onAddNews={handleAddNews}
        onAddDiscussion={handleAddDiscussion}
        onAddDebate={handleAddDebate}
      />

      <div className="canvas-wrapper" ref={reactFlowWrapper}>
        <div className="canvas-flow-pane" ref={flowPaneRef}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onConnectEnd={onConnectEnd}
            isValidConnection={isValidConnection}
            connectionRadius={40}
            onInit={(instance) => { rfInstance.current = instance; }}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{
              type: 'smoothstep',
              animated: true,
              style: { stroke: '#6366f1', strokeWidth: 2 }
            }}
            fitView
            fitViewOptions={{ padding: 0.3, maxZoom: 1.1 }}
            onContextMenu={onContextMenu}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1.5}
              color="#ffb800"
            />
            {showMiniMap && (
              <MiniMap
                className="perspective-minimap"
                style={{ background: '#0d0d14', border: '1px solid #1e1e2e', width: 130, height: 84 }}
                pannable
                zoomable
                nodeColor={(n) => {
                  if (n.type === 'persona') return '#7c3aed';
                  if (n.type === 'news') return '#2563eb';
                  if (n.type === 'analysis') return '#f59e0b';
                  if (n.type === 'discussion') return '#16a34a';
                  if (n.type === 'debate') return '#dc2626';
                  return '#6b7280';
                }}
              />
            )}
            <Controls style={{ background: '#0d0d14', border: '1px solid #1e1e2e', borderRadius: 8 }} />
          </ReactFlow>

          <div className="canvas-watermark" aria-hidden="true">
            <div className="canvas-watermark-logo">
              <span className="logo-ring" />
              <span className="logo-core" />
            </div>
            <div className="canvas-watermark-copy">
              <span className="watermark-kicker">System.Narrative</span>
              <span className="watermark-title">Perspective Canvas</span>
            </div>
          </div>

          {nodes.length === 0 && (
            <div className="empty-hint">
              <div className="hint-icon">⬡</div>
              <div className="hint-title">Perspective Simulator</div>
              <div className="hint-text">Use either: Persona -&gt; News (normal) or 2+ Personas -&gt; Discussion/Debate -&gt; News.</div>
              <div className="hint-steps">
                <span>1. Add Persona nodes</span>
                <span>→</span>
                <span>2. Add News node (for normal) OR add Discussion/Debate node</span>
                <span>→</span>
                <span>3. Connect flow</span>
                <span>→</span>
                <span>4. Normal: Persona -&gt; News | Debate/Discussion: 2+ Personas -&gt; Discussion/Debate -&gt; News</span>
                <span>→</span>
                <span>5. Simulate</span>
              </div>
            </div>
          )}

          {notice && (
            <div className="canvas-notice" role="status" aria-live="polite" key={notice.id}>
              <span className="canvas-notice-text">{notice.text}</span>
              <button
                type="button"
                className="canvas-notice-close"
                onClick={() => setNotice(null)}
                aria-label="Dismiss message"
              >
                ×
              </button>
            </div>
          )}

          {simulationResult && !toastDismissed && (
            <div className={`result-toast ${simulationResult.result_type}`} role="status">
              <span className="toast-icon">
                {simulationResult.result_type === 'debate' ? '⚔️' : simulationResult.result_type === 'analysis' ? '🧠' : '💬'}
              </span>
              <div className="toast-content">
                <div className="toast-type">
                  {simulationResult.result_type === 'debate'
                    ? 'Debate generated'
                    : simulationResult.result_type === 'analysis'
                      ? 'Normal analysis generated'
                      : 'Discussion generated'}
                  {simulationResult.simulated && (
                    <SimulationBadge
                      className="sim-badge-inline"
                      data={{ simulated: true, generation: simulationResult.generation }}
                    />
                  )}
                </div>
                {simulationResult.summary && (
                  <div className="toast-summary">{simulationResult.summary}</div>
                )}
                {simulationResult.simulation_notice && (
                  <div className="toast-notice">{simulationResult.simulation_notice}</div>
                )}
                {summarizeGeneration(simulationResult.generation) && (
                  <div className="toast-generation">{summarizeGeneration(simulationResult.generation)}</div>
                )}
              </div>
              <button
                type="button"
                className="toast-close"
                onClick={() => setToastDismissed(true)}
                aria-label="Dismiss result"
              >
                ×
              </button>
            </div>
          )}
        </div>

        <aside className={`canvas-side-panel ${panelCollapsed ? 'collapsed' : ''}`}>
          <div className="side-panel-head">
            <div>
              <div className="side-panel-kicker">Perspective Nodes</div>
              <div className="side-panel-title">Stacked Feed</div>
            </div>
            <button className="side-panel-collapse" onClick={() => setPanelCollapsed((v) => !v)} suppressHydrationWarning>
              {panelCollapsed ? 'Expand' : 'Collapse'}
            </button>
          </div>

          {!panelCollapsed && (
            <div className="side-panel-body">
              {renderNodeStack('persona', 'Personas')}
              {renderNodeStack('news', 'News Headlines')}
              {renderNodeStack('analysis', 'Analysis')}
              {renderNodeStack('discussion', 'Discussion')}
              {renderNodeStack('debate', 'Debate')}

              {simulationResult && (
                <section className="side-section">
                  <div className="side-section-head">
                    <div className="side-section-title-wrap">
                      <span className="side-dot side-dot-analysis" />
                      <span className="side-section-title">Analysis Output</span>
                    </div>
                    <span className="side-section-count">{analysisEntries.length}</span>
                  </div>

                  {analysisEntries.length === 0 ? (
                    <div className="side-empty">No analysis output yet</div>
                  ) : (
                    <div className="side-stack">
                      {analysisEntries.map((item) => (
                        <button
                          key={item.id}
                          type="button"
                          className={`side-card side-card-${item.type}`}
                          onClick={() => item.nodeId && handlePanelCardClick(item.nodeId)}
                          disabled={!item.nodeId}
                        >
                          <div className="side-card-title">
                            {item.title}
                            {item.simulated && (
                              <SimulationBadge
                                className="sim-badge-inline"
                                data={{ simulated: true, generation: simulationResult?.generation }}
                              />
                            )}
                            {item.generation && <GenerationTag item={item.generation} />}
                          </div>
                          <div className="side-card-sub">{item.text}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </section>
              )}
            </div>
          )}
        </aside>

      </div>
    </div>
  );
}

export default function PerspectiveCanvas() {
  return (
    <ReactFlowProvider>
      <Canvas />
    </ReactFlowProvider>
  );
}
