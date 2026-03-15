"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactFlow, {
  Background, MiniMap, Controls,
  ReactFlowProvider, BackgroundVariant
} from 'reactflow';
import 'reactflow/dist/style.css';

import useGraphStore from '../store/graphStore';
import PersonaNode from '../nodes/PersonaNode';
import NewsNode from '../nodes/NewsNode';
import DiscussionNode from '../nodes/DiscussionNode';
import DebateNode from '../nodes/DebateNode';
import AnalysisNode from '../nodes/AnalysisNode';
import PerspectiveToolbar from './PerspectiveToolbar';
import '../styles/canvas.css';
import '../styles/nodes.css';

const nodeTypes = {
  persona: PersonaNode,
  news: NewsNode,
  discussion: DiscussionNode,
  debate: DebateNode,
  analysis: AnalysisNode,
};

let nodeId = 1;
const nextId = () => `node-${nodeId++}`;

function Canvas() {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, deleteSelectedNodes, focusNode, simulationResult } = useGraphStore();
  const reactFlowWrapper = useRef(null);
  const rfInstance = useRef(null);
  const [collapsedSections, setCollapsedSections] = useState({
    persona: true,
    news: true,
    discussion: true,
    debate: true,
  });

  const [panelCollapsed, setPanelCollapsed] = useState(false);

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

  const handleAddPersona = useCallback((preset) => {
    if (!preset) return;

    const id = nextId();
    const count = nodes.filter(n => n.type === 'persona').length;
    addNode({
      id,
      type: 'persona',
      position: { x: 80 + count * 220, y: 120 },
      data: preset
    });
  }, [nodes, addNode]);

  const handleAddNews = useCallback((preset) => {
    if (!preset) return;

    const id = nextId();
    const count = nodes.filter(n => n.type === 'news').length;
    addNode({
      id,
      type: 'news',
      position: { x: 300 + count * 260, y: 340 },
      data: preset
    });
  }, [nodes, addNode]);

  const handleAddDiscussion = useCallback(() => {
    const id = nextId();
    const count = nodes.filter((n) => n.type === 'discussion').length;
    addNode({
      id,
      type: 'discussion',
      position: { x: 700 + count * 80, y: 560 },
      data: {
        label: 'Discussion'
      }
    });
  }, [nodes, addNode]);

  const handleAddDebate = useCallback(() => {
    const id = nextId();
    const count = nodes.filter((n) => n.type === 'debate').length;
    addNode({
      id,
      type: 'debate',
      position: { x: 900 + count * 80, y: 560 },
      data: {
        label: 'Debate'
      }
    });
  }, [nodes, addNode]);

  const onContextMenu = useCallback((event) => {
    event.preventDefault();
  }, []);

  const groupedNodes = useMemo(() => {
    const byType = {
      persona: nodes.filter((n) => n.type === 'persona'),
      news: nodes.filter((n) => n.type === 'news'),
      analysis: nodes.filter((n) => n.type === 'analysis').slice(-1),
      discussion: nodes.filter((n) => n.type === 'discussion').slice(-1),
      debate: nodes.filter((n) => n.type === 'debate').slice(-1),
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
        <div className="canvas-flow-pane">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={(instance) => { rfInstance.current = instance; }}
            nodeTypes={nodeTypes}
            defaultEdgeOptions={{
              type: 'smoothstep',
              animated: true,
              style: { stroke: '#6366f1', strokeWidth: 2 }
            }}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            onContextMenu={onContextMenu}
            proOptions={{ hideAttribution: true }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={20}
              size={1.5}
              color="#ffb800"
            />
            <MiniMap
              style={{ background: '#0d0d14', border: '1px solid #1e1e2e' }}
              nodeColor={(n) => {
                if (n.type === 'persona') return '#7c3aed';
                if (n.type === 'news') return '#2563eb';
                if (n.type === 'analysis') return '#f59e0b';
                if (n.type === 'discussion') return '#16a34a';
                if (n.type === 'debate') return '#dc2626';
                return '#6b7280';
              }}
            />
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
              <div className="hint-text">Add personas and a news node, connect them, then simulate.</div>
              <div className="hint-steps">
                <span>1. Add Persona nodes</span>
                <span>→</span>
                <span>2. Add News node</span>
                <span>→</span>
                <span>3. Connect edges</span>
                <span>→</span>
                <span>4. Simulate</span>
              </div>
            </div>
          )}

          {simulationResult && (
            <div className={`result-toast ${simulationResult.result_type}`}>
              <span className="toast-icon">
                {simulationResult.result_type === 'debate' ? '⚔️' : simulationResult.result_type === 'analysis' ? '🧠' : '💬'}
              </span>
              <div className="toast-content">
                <div className="toast-type">
                  {simulationResult.result_type === 'debate'
                    ? 'Debate and Discussion generated'
                    : simulationResult.result_type === 'analysis'
                      ? 'Normal analysis generated'
                      : 'Discussion generated'}
                </div>
                {simulationResult.summary && (
                  <div className="toast-summary">{simulationResult.summary}</div>
                )}
              </div>
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
                          <div className="side-card-title">{item.title}</div>
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
