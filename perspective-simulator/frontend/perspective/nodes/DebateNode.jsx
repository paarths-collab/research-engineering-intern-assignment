import { Handle, Position } from 'reactflow';

export default function DebateNode({ data }) {
  return (
    <div className="perspective-node debate-node">
      <div className="node-header">
        <span className="node-icon">⚔️</span>
        <span className="node-type-label">Debate</span>
      </div>
      <div className="node-title">{data.label || 'Debate'}</div>
      {data.description && (
        <div className="node-description">{data.description}</div>
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
      <Handle type="target" position={Position.Top} id="in" />
    </div>
  );
}
