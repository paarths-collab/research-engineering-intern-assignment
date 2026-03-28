"use client";

import { Handle, Position } from 'reactflow';
import useGraphStore from '../store/graphStore';

export default function NewsNode({ id, data, selected }) {
  const deleteNode = useGraphStore((s) => s.deleteNode);

  return (
    <div className={`perspective-node news-node ${selected ? 'selected' : ''}`}>
      <div className="node-header">
        <span className="node-icon">📰</span>
        <span className="node-type-label">News</span>
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
      <div className="node-title">{data.label}</div>
      {data.description && (
        <div className="node-description">{data.description}</div>
      )}
      {data.analysis_summary && (
        <div className="node-analysis">{data.analysis_summary}</div>
      )}
      <Handle type="source" position={Position.Bottom} id="out" />
      <Handle type="target" position={Position.Top} id="in" />
      <Handle type="target" position={Position.Left} id="left" />
      <Handle type="target" position={Position.Right} id="right" />
    </div>
  );
}
