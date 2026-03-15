"use client";
/**
 * IntelligenceGraph.jsx
 *
 * vis-network based 3-layer narrative intelligence graph.
 *
 * Layers (top → bottom):
 *   0  DOMAINS     — purple triangles
 *   1  SUBREDDITS  — blue dots      (core)
 *   2  AUTHORS     — orange squares
 *
 * Edges:
 *   subreddit → subreddit  red     narrative spread
 *   subreddit → domain     cyan    information source
 *   author    → subreddit  yellow  community amplification
 */
import { useRef, useEffect, useCallback } from "react";
import { DataSet, Network } from "vis-network/standalone";

// ── vis-network options ───────────────────────────────────────────────────────
const VIS_OPTIONS = {
  layout: {
    hierarchical: false,
  },
  physics: {
    enabled: true,
    solver: "barnesHut",
    barnesHut: {
      gravitationalConstant: -5000,
      centralGravity: 0.12,
      springLength: 180,
      springConstant: 0.04,
      damping: 0.7,
      avoidOverlap: 1.0,
    },
    stabilization: {
      enabled: true,
      iterations: 200,
      updateInterval: 50,
    },
  },
  interaction: {
    hover: true,
    tooltipDelay: 150,
    zoomView: true,
    dragView: true,
    navigationButtons: false,
    keyboard: false,
  },
  nodes: {
    borderWidth: 1.5,
    borderWidthSelected: 3,
    font: {
      size: 10,
      face: "Inter, system-ui, sans-serif",
    },
    shadow: {
      enabled: true,
      color: "rgba(0,0,0,0.5)",
      size: 8,
      x: 0,
      y: 2,
    },
  },
  edges: {
    color: {
      color: "rgba(255,200,80,0.5)",
      opacity: 0.5,
      highlight: "inherit",
      hover: "rgba(255,214,79,0.8)"
    },
    chosen: {
      edge: (values, id, selected, hovering) => {
        if (selected || hovering) {
          values.opacity = 1.0;
          values.width += 1;
        }
      }
    },
    smooth: {
      enabled: true,
      type: "continuous",
      roundness: 0.3,
    },
    arrows: { to: { enabled: true, scaleFactor: 0.6 } },
    shadow: false,
    hoverWidth: 2,
    selectionWidth: 3,
  },
};



export default function IntelligenceGraph({
  graphData,
  onNodeClick,
  selectedNodeId = null,
  overlayEdges = [], // Narrative spread path [{ source, target, sequence_index }]
}) {
  const containerRef = useRef(null);
  const networkRef = useRef(null);
  const nodesRef = useRef(null);
  const edgesRef = useRef(null);
  const baseNodesRef = useRef(new Map());
  const baseEdgesRef = useRef(new Map());
  const cbRef = useRef(onNodeClick);

  useEffect(() => { cbRef.current = onNodeClick; }, [onNodeClick]);

  // Handle unmount specifically
  useEffect(() => {
    return () => {
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, []);

  // ── Build / synchronize network ──────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || !graphData) return;

    const nodePalette = {
      subreddit: { background: "#3B82F6", border: "#1E40AF" },
      domain: { background: "#8B5CF6", border: "#5B21B6" },
      author: { background: "#F59E0B", border: "#B45309" },
      author_cluster: { background: "#F59E0B", border: "#B45309" },
    };
    const edgePalette = {
      spread: "#EF4444",
      source: "#06B6D4",
      amplifier: "#EAB308",
    };

    const rawNodes = (graphData.nodes || []).map((n) => {
      const palette = nodePalette[n.type] || nodePalette.subreddit;
      return {
        ...n,
        color: {
          background: n.color?.background || palette.background,
          border: n.color?.border || palette.border,
          highlight: { background: "#22C55E", border: "#166534" },
          hover: { background: "#60A5FA", border: n.color?.border || palette.border },
        },
      };
    });

    const rawEdges = (graphData.edges || []).map((e) => {
      let edgeType = e.edge_type;
      if (!edgeType) {
        if (String(e.from || "").startsWith("aut::")) edgeType = "amplifier";
        else if (String(e.to || "").startsWith("dom::")) edgeType = "source";
        else edgeType = "spread";
      }
      return {
        ...e,
        edge_type: edgeType,
        color: {
          color: e.color?.color || edgePalette[edgeType] || "#94A3B8",
          opacity: 0.35,
          hover: e.color?.color || edgePalette[edgeType] || "#94A3B8",
          highlight: e.color?.color || edgePalette[edgeType] || "#94A3B8",
        },
      };
    });

    baseNodesRef.current = new Map(rawNodes.map((n) => [n.id, n]));
    baseEdgesRef.current = new Map(rawEdges.map((e) => [e.id, e]));

    // 1. Initialize Network & DataSets if they don't exist
    if (!networkRef.current) {
        if (rawNodes.length === 0) return;

        nodesRef.current = new DataSet(rawNodes);
        edgesRef.current = new DataSet(rawEdges);

        const network = new Network(
            containerRef.current, 
            { nodes: nodesRef.current, edges: edgesRef.current }, 
            VIS_OPTIONS
        );
        
        // Interaction handlers attached ONCE to the stable DataSet refs
        network.on("click", (params) => {
            if (params.nodes.length > 0) {
                const nodeId = params.nodes[0];
                const nodeData = nodesRef.current.get(nodeId);
                if (cbRef.current) cbRef.current(nodeData);
            } else {
                if (cbRef.current) cbRef.current(null);
            }
        });

        network.on("doubleClick", () => {
            if (cbRef.current) cbRef.current(null);
        });

        networkRef.current = network;
    } else {
        // 2. Incremental Sync using existing stable refs
        const nodes = nodesRef.current;
        const edges = edgesRef.current;

        const currentNodes = nodes.getIds();
        const incomingNodeIds = new Set(rawNodes.map(n => n.id));
        
        nodes.update(rawNodes);
        nodes.remove(currentNodes.filter(id => !incomingNodeIds.has(id)));

        const currentEdges = edges.getIds();
        const incomingEdgeIds = new Set(rawEdges.map(e => e.id));

        edges.update(rawEdges);
        edges.remove(currentEdges.filter(id => !incomingEdgeIds.has(id)));

        if (networkRef.current) {
          networkRef.current.startSimulation();
        }
    }
  }, [graphData]);

  // ── Highlight selected node neighborhood ─────────────────────────────────
  useEffect(() => {
    const net = networkRef.current;
    const nodesDS = nodesRef.current;
    const edgesDS = edgesRef.current;
    if (!net || !graphData || !nodesDS || !edgesDS) {
      return;
    }

    if (!selectedNodeId) {
      const resetNodes = Array.from(baseNodesRef.current.values()).map((n) => ({
        id: n.id,
        size: n.size,
        color: n.color,
        borderWidth: 1.5,
        font: n.font,
      }));
      const resetEdges = Array.from(baseEdgesRef.current.values()).map((e) => ({
        id: e.id,
        width: e.width,
        color: { ...e.color, opacity: 0.35 },
      }));
      nodesDS.update(resetNodes);
      edgesDS.update(resetEdges);
      if (overlayEdges.length === 0) {
        net.unselectAll();
      }
      return;
    }

    try {
      const exists = net.body.data.nodes.get(selectedNodeId);
      if (!exists) return;

      const neighborIds = new Set(net.getConnectedNodes(selectedNodeId));
      const edgeIds = new Set(net.getConnectedEdges(selectedNodeId));
      const relatedNodeIds = new Set([selectedNodeId, ...Array.from(neighborIds)]);

      const nodeUpdates = Array.from(baseNodesRef.current.values()).map((n) => {
        const isSelected = n.id === selectedNodeId;
        const isNeighbor = neighborIds.has(n.id);
        const isRelated = relatedNodeIds.has(n.id);
        const nextColor = isSelected
          ? { ...n.color, background: "#22C55E", border: "#166534" }
          : isNeighbor
            ? { ...n.color, border: "#22C55E" }
            : { ...n.color, opacity: 0.2 };

        return {
          id: n.id,
          size: isSelected ? Math.max((n.size || 16) * 1.5, 18) : n.size,
          color: nextColor,
          borderWidth: isRelated ? 3 : 1,
          font: {
            ...(n.font || {}),
            color: isRelated ? "#ffffff" : "rgba(255,255,255,0.3)",
          },
        };
      });

      const edgeUpdates = Array.from(baseEdgesRef.current.values()).map((e) => {
        const isRelated = edgeIds.has(e.id);
        return {
          id: e.id,
          width: isRelated ? 5 : 1,
          color: {
            ...(e.color || {}),
            opacity: isRelated ? 1.0 : 0.1,
          },
        };
      });

      nodesDS.update(nodeUpdates);
      edgesDS.update(edgeUpdates);

      net.selectNodes(Array.from(relatedNodeIds), false);
      net.selectEdges(Array.from(edgeIds));

      net.focus(selectedNodeId, {
        scale: 1.1,
        animation: { duration: 500, easingFunction: "easeInOutQuad" },
      });
    } catch (err) {
      console.warn("Graph interaction error:", err);
    }
  }, [selectedNodeId, graphData, overlayEdges]);

  // ── Narrative Overlay Highlight ──────────────────────────────────────────
  useEffect(() => {
    const net = networkRef.current;
    if (!net || !edgesRef.current || selectedNodeId) return;

    const edgesDS = edgesRef.current;
    const allEdges = edgesDS.get();

    if (overlayEdges.length === 0) {
      // Restore default edge opacities/widths if no overlay
      const updates = allEdges.map(e => ({
        id: e.id,
        color: { opacity: 0.35, color: e.color?.color || "rgba(148,163,184,0.5)" },
        width: 1
      }));
      edgesDS.update(updates);
      return;
    }

    // Match overlay edges (source -> target) to graph edges
    const overlayEdgeSet = new Set(overlayEdges.map(oe => `${oe.source}→${oe.target}`));
    const matchedIds = [];

    const updates = allEdges.map(e => {
        const key = `${e.from}→${e.to}`;
        const isMatched = overlayEdgeSet.has(key);
        if (isMatched) matchedIds.push(e.id);

        return {
            id: e.id,
            color: { 
            opacity: isMatched ? 1.0 : 0.2,
          color: isMatched ? "#22C55E" : "rgba(148,163,184,0.45)" 
            },
            width: isMatched ? 5 : 1,
        }
    });

    edgesDS.update(updates);
    
    // Select matched edges and nodes
    if (matchedIds.length > 0) {
        const nodeIds = Array.from(new Set(overlayEdges.flatMap(oe => [oe.source, oe.target])));
        net.selectNodes(nodeIds, false);
        net.selectEdges(matchedIds);
        
        // Fit view to overlay
        net.fit({ nodes: nodeIds, animation: { duration: 700, easingFunction: "easeInOutQuad" } });
    }
  }, [overlayEdges, selectedNodeId]);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
        background: "radial-gradient(circle at 20% 20%, #171103 0%, #090704 60%, #050403 100%)",
        cursor: "grab",
      }}
    />
  );
}
