"use client";
import { useRef, useEffect, useState } from "react";
import * as d3 from "d3";

// ── Constants ─────────────────────────────────────────────────────────────────
const SUB_COLOR  = "#00838F"; // Darker cyan for light BG
const USR_COLOR  = "#E65100"; // Darker orange for light BG
const ACCENT     = "#334155"; // Dark slate for readable labels on light BG

const CLUSTER_COLORS = [
  "#D32F2F", "#0288D1", "#388E3C", "#7B1FA2",
  "#F57C00", "#E64A19", "#0097A7", "#43A047",
  "#C2185B", "#455A64",
];

function clusterColor(cluster) {
  const idx = parseInt(String(cluster), 10);
  return isNaN(idx) ? "rgba(0,0,0,0.3)" : CLUSTER_COLORS[idx % CLUSTER_COLORS.length];
}

function nodeRadius(node) {
  if (node.type === "subreddit") {
    const posts = node.total_duplicate_posts || 1;
    return Math.max(18, Math.min(55, Math.pow(posts, 0.4)));
  }
  const inf = typeof node.final_influence_score === "number" ? node.final_influence_score : 0;
  return Math.max(6, Math.min(22, 5 + inf * 10));
}

// ── Highlight helper (imperative, no simulation restart) ──────────────────────
function applyHighlight(nodeId, edgeId, draw) {
  if (!draw.nodeElements || !draw.edgeElements) return;

  if (!nodeId && !edgeId) {
    draw.nodeElements.select("circle").attr("opacity", 1).attr("stroke-opacity", 0.6);
    draw.nodeElements.select("text").attr("opacity", 0.8);
    draw.edgeElements.attr("stroke-opacity", 0.65).attr("stroke-width", 3.5);
    return;
  }

  // Build a reliable lookup map for node neighbors
  const linkedByIndex = {};
  draw.edgeElements.each((d) => {
    const sid = typeof d.source === "object" ? d.source.id : d.source;
    const tid = typeof d.target === "object" ? d.target.id : d.target;
    linkedByIndex[`${sid},${tid}`] = true;
    linkedByIndex[`${tid},${sid}`] = true;
  });

  // Dim everything first
  draw.nodeElements.select("circle").attr("opacity", 0.3).attr("stroke-opacity", 0.15);
  draw.nodeElements.select("text").attr("opacity", 0.2);
  draw.edgeElements.attr("stroke-opacity", 0.15).attr("stroke-width", 1);

  if (nodeId) {
    // Highlight connected edges
    draw.edgeElements
      .filter((d) => {
        const sid = typeof d.source === "object" ? d.source.id : d.source;
        const tid = typeof d.target === "object" ? d.target.id : d.target;
        return sid === nodeId || tid === nodeId;
      })
      .attr("stroke-opacity", 0.9)
      .attr("stroke-width", 2.2);

    // Highlight connected nodes + self
    draw.nodeElements
      .filter((d) => linkedByIndex[`${nodeId},${d.id}`] || d.id === nodeId)
      .select("circle")
      .attr("opacity", 1)
      .attr("stroke-opacity", 1);

    draw.nodeElements
      .filter((d) => linkedByIndex[`${nodeId},${d.id}`] || d.id === nodeId)
      .select("text")
      .attr("opacity", 1);
  } else if (edgeId) {
    let focusSid, focusTid;
    draw.edgeElements
      .filter((d) => {
        const match = String(d.id) === String(edgeId) || String(d.narrative_id) === String(edgeId);
        if (match) {
          focusSid = typeof d.source === "object" ? d.source.id : d.source;
          focusTid = typeof d.target === "object" ? d.target.id : d.target;
        }
        return match;
      })
      .attr("stroke-opacity", 1)
      .attr("stroke-width", 3.5);

    if (focusSid || focusTid) {
      draw.nodeElements
        .filter((d) => d.id === focusSid || d.id === focusTid)
        .select("circle")
        .attr("opacity", 1)
        .attr("stroke-opacity", 1);

      draw.nodeElements
        .filter((d) => d.id === focusSid || d.id === focusTid)
        .select("text")
        .attr("opacity", 1);
    }
  }
}

// ── Tooltip components ────────────────────────────────────────────────────────
function stat(label, value) {
  if (value == null) return null;
  return (
    <div key={label} className="flex justify-between gap-4">
      <span style={{ color: "rgba(255,255,255,0.4)" }}>{label}</span>
      <span style={{ color: "rgba(255,255,255,0.9)" }}>{value}</span>
    </div>
  );
}

function SubredditTooltip({ d }) {
  return (
    <div className="space-y-1">
      <div className="text-[12px] font-black font-mono mb-2" style={{ color: ACCENT }}>
        r/{d.label}
      </div>
      {stat("Posts", d.total_duplicate_posts?.toLocaleString())}
      {stat("Narratives", d.unique_narratives?.toLocaleString())}
      {stat("Users", d.unique_users?.toLocaleString())}
      {d.echo_score != null && stat("Echo Score", d.echo_score.toFixed(2))}
      {d.top_domains && (
        <div className="mt-1 pt-1" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 10 }}>{d.top_domains}</span>
        </div>
      )}
    </div>
  );
}

function UserTooltip({ d }) {
  return (
    <div className="space-y-1">
      <div className="text-[12px] font-black font-mono mb-2" style={{ color: USR_COLOR }}>
        u/{d.label}
      </div>
      {stat("Influence", d.final_influence_score != null ? d.final_influence_score.toFixed(2) : null)}
      {stat("Narratives", d.unique_narratives?.toLocaleString())}
      {stat("Communities", d.communities_active_in)}
      {stat("Amplification", d.total_relative_amplification != null ? d.total_relative_amplification.toFixed(1) : null)}
      {d.most_common_domain && (
        <div className="mt-1 pt-1" style={{ borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <span style={{ color: "rgba(255,255,255,0.4)", fontSize: 10 }}>{d.most_common_domain}</span>
        </div>
      )}
    </div>
  );
}

function EdgeTooltip({ d }) {
  const isLabelMe = typeof d.topic_label === 'string' && d.topic_label.startsWith("LABEL_ME");
  const displayLabel = isLabelMe ? "Generated Topic" : d.topic_label;

  return (
    <div className="space-y-1">
      <div className="text-[11px] font-mono mb-2 leading-snug" style={{ color: "rgba(255,255,255,0.8)", maxWidth: 260 }}>
        {d.title?.length > 80 ? d.title.slice(0, 80) + "…" : d.title}
      </div>
      {displayLabel && (
        <div className="text-[10px] font-mono px-1.5 py-0.5 inline-block" style={{
          background: `${clusterColor(d.topic_cluster)}18`,
          border: `1px solid ${clusterColor(d.topic_cluster)}50`,
          color: clusterColor(d.topic_cluster),
        }}>
          {displayLabel}
        </div>
      )}
      <div className="mt-1 space-y-0.5">
        {stat("Domain", d.domain)}
        {d.score != null && stat("Score", Math.round(d.score))}
        {d.hours_from_origin != null && stat("Hours from origin", d.hours_from_origin.toFixed(1) + "h")}
      </div>
      <div className="mt-1.5 text-[9px] font-mono font-bold" style={{ color: "rgba(0,229,255,0.7)" }}>
        Passive Edge Relationship
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ForceGraph({
  nodes = [],
  edges = [],
  selectedCluster = null,
  highlightNodeId = null,
  highlightEdgeId = null,
  onNodeClick,
  onEdgeClick,
}) {
  const containerRef = useRef(null);
  const drawRef      = useRef({});
  const simRef       = useRef(null);
  const cbRef        = useRef({ onNodeClick, onEdgeClick });

  // Always-fresh callbacks (no stale closures in D3 handlers)
  useEffect(() => {
    cbRef.current = { onNodeClick, onEdgeClick };
  }, [onNodeClick, onEdgeClick]);

  const [tooltip, setTooltip] = useState(null); // { x, y, type, data }

  // ── Build/rebuild simulation ────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || nodes.length === 0) return;

    const container = containerRef.current;
    const W = container.clientWidth  || 800;
    const H = container.clientHeight || 600;

    // Stop old simulation
    if (simRef.current) simRef.current.stop();

    // Clear previous SVG
    d3.select(container).selectAll("svg").remove();
    setTooltip(null);

    // ── SVG ─────────────────────────────────────────────────────────────────
    const svg = d3.select(container)
      .append("svg")
      .attr("width", "100%")
      .attr("height", "100%")
      .style("background", "transparent")
      .style("cursor", "grab");

    // Defs — glow filters
    const defs = svg.append("defs");

    ["glow-sub", "glow-usr", "glow-edge"].forEach((id, i) => {
      const f = defs.append("filter").attr("id", id).attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
      f.append("feGaussianBlur").attr("stdDeviation", [5, 2.5, 3][i]).attr("result", "blur");
      const merge = f.append("feMerge");
      merge.append("feMergeNode").attr("in", "blur");
      merge.append("feMergeNode").attr("in", "SourceGraphic");
    });

    // ── Zoom/pan ────────────────────────────────────────────────────────────
    const g = svg.append("g");

    const zoom = d3.zoom()
      .scaleExtent([0.08, 8])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
        svg.style("cursor", event.transform.k > 1 ? "grabbing" : "grab");
      });

    svg.call(zoom).on("dblclick.zoom", null);

    // Click canvas background → deselect
    svg.on("click", () => {
      drawRef.current.selectedEdgeId = null;
      if (cbRef.current.onNodeClick) cbRef.current.onNodeClick(null);
      if (cbRef.current.onEdgeClick) cbRef.current.onEdgeClick(null);
    });

    // ── Filter by selectedCluster ────────────────────────────────────────────
    const filteredEdges = selectedCluster
      ? edges.filter(e => String(e.topic_cluster) === String(selectedCluster))
      : edges;

    // Only include user nodes that appear in filtered edges + all subreddit nodes
    const activeIds = new Set();
    filteredEdges.forEach(e => { activeIds.add(e.source); activeIds.add(e.target); });
    nodes.filter(n => n.type === "subreddit").forEach(n => activeIds.add(n.id));

    const simNodes = nodes
      .filter(n => activeIds.has(n.id))
      .map(n => ({ ...n, r: nodeRadius(n) }));

    const nodeById = new Map(simNodes.map(n => [n.id, n]));

    const simEdges = filteredEdges
      .filter(e => nodeById.has(e.source) && nodeById.has(e.target))
      .map(e => ({ ...e, source: e.source, target: e.target })); // D3 mutates source/target to objects

    // ── Simulation ──────────────────────────────────────────────────────────
    const sim = d3.forceSimulation(simNodes)
      .force("link",
        d3.forceLink(simEdges)
          .id(d => d.id)
          .distance(d => {
            const tgt = typeof d.target === "object" ? d.target : nodeById.get(d.target);
            return tgt?.type === "subreddit" ? 140 : 70;
          })
          .strength(0.25)
      )
      .force("charge",
        d3.forceManyBody().strength(d => d.type === "subreddit" ? -600 : -90)
      )
      .force("center", d3.forceCenter(W / 2, H / 2).strength(0.08))
      .force("collide", d3.forceCollide().radius(d => d.r + 5).strength(0.7))
      .alphaDecay(0.025);

    simRef.current = sim;

    // ── Draw edges ──────────────────────────────────────────────────────────
    const edgeG = g.append("g").attr("class", "edges");
    
    // Invisible hit-area lines (much thicker targets)
    const hitElements = edgeG
      .selectAll("line.hit")
      .data(simEdges)
      .join("line")
      .attr("class", "hit")
      .attr("stroke", "transparent")
      .attr("stroke-width", 16)
      .style("cursor", "pointer")
      .on("mouseenter", function (event, d) {
        const [mx, my] = d3.pointer(event, container);
        setTooltip({ x: mx, y: my, type: "edge", data: d });
      })
      .on("mouseleave", function (event, d) {
        setTooltip(null);
      })
      .on("click", function (event, d) {
        event.stopPropagation();
        if (cbRef.current.onEdgeClick) cbRef.current.onEdgeClick(d);
      });

    const edgeElements = edgeG
      .selectAll("line.visible")
      .data(simEdges)
      .join("line")
      .attr("class", "visible")
      .attr("stroke", d => clusterColor(d.topic_cluster))
      .attr("stroke-width", 3.5)
      .attr("stroke-opacity", 0.65)
      .attr("stroke-linecap", "round")
      .style("pointer-events", "none"); // Events pass through to hit layer

    // ── Draw nodes ──────────────────────────────────────────────────────────
    const nodeG = g.append("g").attr("class", "nodes");
    const nodeElements = nodeG
      .selectAll("g.node")
      .data(simNodes)
      .join("g")
      .attr("class", "node")
      .style("cursor", "pointer")
      .call(
        d3.drag()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on("drag",  (event, d) => { d.fx = event.x; d.fy = event.y; })
          .on("end",   (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      )
      .on("mouseenter", function (event, d) {
        const [mx, my] = d3.pointer(event, container);
        setTooltip({ x: mx, y: my, type: "node", data: d });
      })
      .on("mouseleave", function () {
        setTooltip(null);
      })
      .on("click", function (event, d) {
        event.stopPropagation();
        if (cbRef.current.onNodeClick) cbRef.current.onNodeClick(d);
      });

    // Circle
    nodeElements.append("circle")
      .attr("r", d => d.r)
      .attr("fill",   d => d.type === "subreddit" ? `${SUB_COLOR}20` : `${USR_COLOR}18`)
      .attr("stroke", d => d.type === "subreddit" ? SUB_COLOR : USR_COLOR)
      .attr("stroke-width", 1.5)
      .attr("stroke-opacity", 0.6)
      .attr("filter",  d => d.type === "subreddit" ? "url(#glow-sub)" : null);

    // Subreddit label (always shown)
    nodeElements.filter(d => d.type === "subreddit")
      .append("text")
      .text(d => `r/${d.label}`)
      .attr("text-anchor", "middle")
      .attr("dy", d => d.r + 13)
      .attr("fill", ACCENT)
      .attr("font-size", "9px")
      .attr("font-family", "monospace")
      .attr("opacity", 0.8)
      .style("pointer-events", "none");

    // ── Store selections for imperative updates ──────────────────────────────
    drawRef.current = { nodeElements, edgeElements, selectedEdgeId: null };

    // ── Simulation tick ──────────────────────────────────────────────────────
    sim.on("tick", () => {
      [edgeElements, hitElements].forEach(sel => {
        sel
          .attr("x1", d => (typeof d.source === "object" ? d.source : nodeById.get(d.source))?.x ?? 0)
          .attr("y1", d => (typeof d.source === "object" ? d.source : nodeById.get(d.source))?.y ?? 0)
          .attr("x2", d => (typeof d.target === "object" ? d.target : nodeById.get(d.target))?.x ?? 0)
          .attr("y2", d => (typeof d.target === "object" ? d.target : nodeById.get(d.target))?.y ?? 0);
      });

      nodeElements.attr("transform", d => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });

    // Apply current highlight immediately after building
    applyHighlight(highlightNodeId, highlightEdgeId, drawRef.current);

    return () => sim.stop();
    // highlightNodeId intentionally excluded — managed by separate effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, selectedCluster]);

  // ── Imperative highlight update ─────────────────────────────────────────────
  useEffect(() => {
    applyHighlight(highlightNodeId, highlightEdgeId, drawRef.current);
  }, [highlightNodeId, highlightEdgeId]);

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%", position: "relative" }}>
      {tooltip && (
        <div
          style={{
            position: "absolute",
            left: Math.min(tooltip.x + 14, (containerRef.current?.clientWidth ?? 800) - 280),
            top:  Math.max(tooltip.y - 20, 8),
            zIndex: 50,
            pointerEvents: "none",
          }}
        >
          <div
            className="p-3 font-mono text-[11px]"
            style={{
              background:   "rgba(5,7,10,0.96)",
              border:        "1px solid rgba(0,229,255,0.18)",
              boxShadow:     "0 8px 32px rgba(0,0,0,0.6)",
              backdropFilter:"blur(12px)",
              minWidth:       180,
              maxWidth:       280,
            }}
          >
            {tooltip.type === "node"
              ? (tooltip.data.type === "subreddit"
                ? <SubredditTooltip d={tooltip.data} />
                : <UserTooltip      d={tooltip.data} />)
              : <EdgeTooltip d={tooltip.data} />
            }
          </div>
        </div>
      )}
    </div>
  );
}
