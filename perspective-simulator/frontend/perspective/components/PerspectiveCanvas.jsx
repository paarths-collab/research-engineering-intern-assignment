import { useCallback, useRef } from 'react';
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
import PerspectiveToolbar from './PerspectiveToolbar';
import '../styles/canvas.css';
import '../styles/nodes.css';

const nodeTypes = {
  persona: PersonaNode,
  news: NewsNode,
  discussion: DiscussionNode,
  debate: DebateNode,
};

let nodeId = 1;
const nextId = () => `node-${nodeId++}`;

function Canvas() {
  const { nodes, edges, onNodesChange, onEdgesChange, onConnect, addNode, simulationResult } = useGraphStore();
  const reactFlowWrapper = useRef(null);
  const [reactFlowInstance, setReactFlowInstance] = import('react').then ? null : null;
  const rfInstance = useRef(null);

  const handleAddPersona = useCallback((preset) => {
    const id = nextId();
    const count = nodes.filter(n => n.type === 'persona').length;
    addNode({
      id,
      type: 'persona',
      position: { x: 80 + count * 220, y: 120 },
      data: preset || {
        label: `Persona ${count + 1}`,
        type: 'persona',
        traits: ['edit traits'],
        ideology_vector: [0.5, 0.5, 0.5, 0.5]
      }
    });
  }, [nodes, addNode]);

  const handleAddNews = useCallback((preset) => {
    const id = nextId();
    const count = nodes.filter(n => n.type === 'news').length;
    addNode({
      id,
      type: 'news',
      position: { x: 300 + count * 260, y: 340 },
      data: preset || {
        label: `News Headline ${count + 1}`,
        type: 'news',
        description: 'Add a description...'
      }
    });
  }, [nodes, addNode]);

  const onContextMenu = useCallback((event) => {
    event.preventDefault();
  }, []);

  return (
    <div className="perspective-layout">
      <PerspectiveToolbar onAddPersona={handleAddPersona} onAddNews={handleAddNews} />

      <div className="canvas-wrapper" ref={reactFlowWrapper}>
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
            gap={24}
            size={1}
            color="#2a2a3a"
          />
          <MiniMap
            style={{ background: '#0d0d14', border: '1px solid #1e1e2e' }}
            nodeColor={(n) => {
              if (n.type === 'persona') return '#7c3aed';
              if (n.type === 'news') return '#2563eb';
              if (n.type === 'discussion') return '#16a34a';
              if (n.type === 'debate') return '#dc2626';
              return '#6b7280';
            }}
          />
          <Controls style={{ background: '#0d0d14', border: '1px solid #1e1e2e', borderRadius: 8 }} />
        </ReactFlow>

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
              {simulationResult.result_type === 'debate' ? '⚔️' : '💬'}
            </span>
            <div className="toast-content">
              <div className="toast-type">
                {simulationResult.result_type === 'debate' ? 'Debate detected' : 'Discussion generated'}
              </div>
              {simulationResult.summary && (
                <div className="toast-summary">{simulationResult.summary}</div>
              )}
            </div>
          </div>
        )}
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
