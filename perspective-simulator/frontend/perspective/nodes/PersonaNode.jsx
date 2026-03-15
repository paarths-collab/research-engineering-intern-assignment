import { Handle, Position } from 'reactflow';

export default function PersonaNode({ data, selected }) {
  return (
    <div className={`perspective-node persona-node ${selected ? 'selected' : ''}`}>
      <div className="node-header">
        <span className="node-icon">👤</span>
        <span className="node-type-label">Persona</span>
      </div>
      <div className="node-title">{data.label}</div>
      {data.traits && data.traits.length > 0 && (
        <div className="node-traits">
          {data.traits.slice(0, 3).map((trait, i) => (
            <span key={i} className="trait-pill">{trait}</span>
          ))}
        </div>
      )}
      <Handle type="source" position={Position.Right} id="out" />
      <Handle type="target" position={Position.Left} id="in" />
    </div>
  );
}
