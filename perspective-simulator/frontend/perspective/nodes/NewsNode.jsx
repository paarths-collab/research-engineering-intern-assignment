import { Handle, Position } from 'reactflow';

export default function NewsNode({ data, selected }) {
  return (
    <div className={`perspective-node news-node ${selected ? 'selected' : ''}`}>
      <div className="node-header">
        <span className="node-icon">📰</span>
        <span className="node-type-label">News</span>
      </div>
      <div className="node-title">{data.label}</div>
      {data.description && (
        <div className="node-description">{data.description}</div>
      )}
      <Handle type="source" position={Position.Bottom} id="out" />
      <Handle type="target" position={Position.Top} id="in" />
      <Handle type="target" position={Position.Left} id="left" />
      <Handle type="target" position={Position.Right} id="right" />
    </div>
  );
}
