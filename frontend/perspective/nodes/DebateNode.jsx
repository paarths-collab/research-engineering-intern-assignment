"use client";

import { Handle, Position } from 'reactflow';
import useGraphStore from '../store/graphStore';

export default function DebateNode({ id, data, selected }) {
  const deleteNode = useGraphStore((s) => s.deleteNode);
  const reactions = Array.isArray(data?.reactions) ? data.reactions : [];
  const rounds = Array.isArray(data?.rounds) ? data.rounds : [];

  return (
    <div className={`perspective-node debate-node ${selected ? 'selected' : ''}`}>
      <div className="node-header">
        <span className="node-icon">⚔️</span>
        <span className="node-type-label">Debate</span>
        <button
          className="node-delete-btn"
          onClick={(e) => {
            e.stopPropagation();
            deleteNode(id);
          }}
          title="Delete node"
          aria-label="Delete node"
        >
          ×
        </button>
      </div>
      <div className="node-title">{data.label || 'Debate'}</div>
      {(data.summary || data.description) && (
        <div className="node-description">{data.summary || data.description}</div>
      )}
      {rounds.length > 0 && (
        <div className="node-rounds">
          {rounds.map((round) => (
            <div key={round.round} className="node-round-card">
              <div className="node-round-title">{round.title || `Round ${round.round}`}</div>
              {round.summary && <div className="node-round-summary">{round.summary}</div>}
              <div className="node-round-turns">
                {(Array.isArray(round.turns) ? round.turns : []).map((turn, idx) => (
                  <div key={`${round.round}-${idx}`} className="node-analysis-item">
                    <span className="node-analysis-persona">{turn.persona}:</span> {turn.text}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {reactions.length > 0 && rounds.length === 0 && (
        <div className="node-analysis-list">
          {reactions.map((item, idx) => (
            <div key={`${item.persona}-${idx}`} className="node-analysis-item">
              <span className="node-analysis-persona">{item.persona}:</span> {item.reaction}
            </div>
          ))}
        </div>
      )}
      {data.ideology_distance !== undefined && (
        <div className="ideology-meter">
          <div className="meter-label">Conflict</div>
          <div className="meter-bar">
            <div
              className="meter-fill debate-fill"
              style={{ width: `${Math.round(data.ideology_distance * 100)}%` }}
            />
          </div>
        </div>
      )}
      <Handle type="target" position={Position.Top} id="in-top" />
      <Handle type="target" position={Position.Left} id="in-left" />
      <Handle type="target" position={Position.Right} id="in-right" />
      <Handle type="source" position={Position.Bottom} id="out-bottom" />
      <Handle type="source" position={Position.Left} id="out-left" />
      <Handle type="source" position={Position.Right} id="out-right" />
    </div>
  );
}
