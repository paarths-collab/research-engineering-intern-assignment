import { Handle, Position } from 'reactflow';

export default function DiscussionNode({ data }) {
  return (
    <div className="perspective-node discussion-node">
      <div className="node-header">
        <span className="node-icon">💬</span>
        <span className="node-type-label">Discussion</span>
      </div>
      <div className="node-title">{data.label || 'Discussion'}</div>
      {data.description && (
        <div className="node-description">{data.description}</div>
      )}
      {data.ideology_distance !== undefined && (
        <div className="ideology-meter">
          <div className="meter-label">Alignment</div>
          <div className="meter-bar">
            <div
              className="meter-fill discussion-fill"
              style={{ width: `${Math.round((1 - data.ideology_distance) * 100)}%` }}
            />
          </div>
        </div>
      )}
      <Handle type="target" position={Position.Top} id="in" />
    </div>
  );
}
