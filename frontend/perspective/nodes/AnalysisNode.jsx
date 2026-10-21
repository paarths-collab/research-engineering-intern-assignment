"use client";

import { Handle, Position } from 'reactflow';
import useGraphStore from '../store/graphStore';
import { SimulationBadge, GenerationTag, ReactionSources } from './SimulationBadge';

export default function AnalysisNode({ id, data, selected }) {
  const deleteNode = useGraphStore((s) => s.deleteNode);
  const reactions = Array.isArray(data?.reactions) ? data.reactions : [];
  const turns = Array.isArray(data?.turns) ? data.turns : [];

  return (
    <div className={`perspective-node analysis-node ${selected ? 'selected' : ''}`}>
      <div className="node-header">
        <span className="node-icon">🧠</span>
        <span className="node-type-label">Analysis</span>
        <SimulationBadge data={data} />
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

      <div className="node-title">{data.label || 'Analysis'}</div>
      {(data.summary || data.description) && (
        <div className="node-description">{data.summary || data.description}</div>
      )}

      {data?.round && (
        <div className="node-analysis-more">Round {data.round} {data.mode ? `(${data.mode})` : ''}</div>
      )}

      {turns.length > 0 && (
        <div className="node-analysis-list">
          {turns.map((turn, idx) => (
            <div key={`${turn.persona || 'persona'}-${idx}`} className="node-analysis-item">
              <span className="node-analysis-persona">{turn.persona || 'Persona'}:</span> <GenerationTag item={turn} /> {turn.text || turn.answer || ''}
            </div>
          ))}
        </div>
      )}

      {turns.length > 0 && <ReactionSources reactions={reactions} />}
      {reactions.length > 0 && turns.length === 0 && (
        <div className="node-analysis-list">
          {reactions.slice(0, 2).map((item, idx) => (
            <div key={`${item.persona}-${idx}`} className="node-analysis-item">
              <span className="node-analysis-persona">{item.persona}:</span> <GenerationTag item={item} /> {item.reaction}
            </div>
          ))}
          {reactions.length > 2 && (
            <div className="node-analysis-more">+{reactions.length - 2} more reactions</div>
          )}
        </div>
      )}

      <Handle type="target" position={Position.Top} id="in" />
    </div>
  );
}
