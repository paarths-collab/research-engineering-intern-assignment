"use client";
import { useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";

// Fixed palette for the 5 narrative clusters — golden design system
const CLUSTER_COLORS = {
  "Geopolitics":         "#FFB800",
  "US Politics":         "#FF4081",
  "Economy":             "#00BCD4",
  "Technology":          "#AB47BC",
  "Culture":             "#66BB6A",
};
const FALLBACK_COLORS = ["#EF5350","#42A5F5","#FFA726","#26C6DA","#EC407A"];

const SPIKE_THRESHOLD = 2.0;

function buildChart(container, svgEl, streamData, onSpikeClick) {
  const rect = container.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  if (width < 10 || height < 10) return;

  const margin = { top: 24, right: 24, bottom: 60, left: 44 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  d3.select(svgEl).selectAll("*").remove();

  const svg = d3.select(svgEl)
    .attr("width", width)
    .attr("height", height);

  const defs = svg.append("defs");

  // Spike glow filter
  const glow = defs.append("filter")
    .attr("id", "spike-glow")
    .attr("x", "-100%").attr("y", "-100%")
    .attr("width", "300%").attr("height", "300%");
  glow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "5").attr("result", "blur");
  const fm = glow.append("feMerge");
  fm.append("feMergeNode").attr("in", "blur");
  fm.append("feMergeNode").attr("in", "SourceGraphic");

  const critGlow = defs.append("filter")
    .attr("id", "critical-glow")
    .attr("x", "-100%").attr("y", "-100%")
    .attr("width", "300%").attr("height", "300%");
  critGlow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "8").attr("result", "blur");
  const fm2 = critGlow.append("feMerge");
  fm2.append("feMergeNode").attr("in", "blur");
  fm2.append("feMergeNode").attr("in", "SourceGraphic");

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  const keys = streamData.keys;
  const data = streamData.data.map(d => ({ ...d, date: new Date(d.date) }));
  data.sort((a, b) => a.date - b.date);

  if (data.length < 2) return;

  const xScale = d3.scaleTime()
    .domain(d3.extent(data, d => d.date))
    .range([0, innerW]);

  const stack = d3.stack()
    .keys(keys)
    .offset(d3.stackOffsetWiggle)
    .order(d3.stackOrderInsideOut);

  const layers = stack(data);

  const yMin = d3.min(layers, l => d3.min(l, d => d[0]));
  const yMax = d3.max(layers, l => d3.max(l, d => d[1]));
  const yScale = d3.scaleLinear()
    .domain([yMin, yMax])
    .range([innerH, 0]);

  const area = d3.area()
    .x(d => xScale(d.data.date))
    .y0(d => yScale(d[0]))
    .y1(d => yScale(d[1]))
    .curve(d3.curveCatmullRom);

  // Grid
  g.append("g")
    .attr("class", "grid")
    .call(
      d3.axisBottom(xScale).ticks(10).tickSize(innerH).tickFormat("")
    )
    .call(ax => {
      ax.select(".domain").remove();
      ax.selectAll("line")
        .attr("stroke", "rgba(255,255,255,0.04)")
        .attr("stroke-dasharray", "2 4");
    });

  // Stream layers
  const layerGroup = g.append("g").attr("class", "stream-layers");

  layerGroup.selectAll(".stream-layer")
    .data(layers)
    .enter()
    .append("path")
    .attr("class", "stream-layer")
    .attr("data-key", d => d.key)
    .attr("d", area)
    .attr("fill", d => CLUSTER_COLORS[d.key] || FALLBACK_COLORS[keys.indexOf(d.key) % FALLBACK_COLORS.length])
    .attr("fill-opacity", 0.65)
    .attr("stroke", d => CLUSTER_COLORS[d.key] || FALLBACK_COLORS[keys.indexOf(d.key) % FALLBACK_COLORS.length])
    .attr("stroke-width", 0.4)
    .attr("stroke-opacity", 0.25)
    .style("cursor", "pointer")
    .on("mouseover", function (_, d) {
      layerGroup.selectAll(".stream-layer").attr("fill-opacity", 0.12);
      d3.select(this).attr("fill-opacity", 0.92).attr("stroke-opacity", 0.6);
    })
    .on("mouseout", function () {
      layerGroup.selectAll(".stream-layer")
        .attr("fill-opacity", 0.65)
        .attr("stroke-opacity", 0.25);
    });

  // X axis
  g.append("g")
    .attr("transform", `translate(0,${innerH})`)
    .call(
      d3.axisBottom(xScale).ticks(8).tickFormat(d3.timeFormat("%b '%y"))
    )
    .call(ax => {
      ax.select(".domain").attr("stroke", "rgba(255,255,255,0.08)");
      ax.selectAll("line").attr("stroke", "rgba(255,255,255,0.08)");
      ax.selectAll("text")
        .attr("fill", "rgba(255,255,255,0.35)")
        .style("font-size", "10px")
        .style("font-family", "monospace")
        .attr("dy", "1.2em");
    });

  // Spike markers — from streamData.spikes (per-cluster)
  const spikes = streamData.spikes || [];
  const spikeG = g.append("g").attr("class", "spike-markers");

  spikes.forEach(spike => {
    const x = xScale(new Date(spike.date));
    if (isNaN(x)) return;

    const isCritical = (spike.z_score || 0) >= 3.0;
    const clusterColor = CLUSTER_COLORS[spike.cluster] || "#FFB800";
    const spikeColor   = isCritical ? "#FF4081" : clusterColor;
    const dotY         = innerH * 0.15;

    spikeG.append("line")
      .attr("x1", x).attr("y1", 0)
      .attr("x2", x).attr("y2", innerH)
      .attr("stroke", spikeColor)
      .attr("stroke-width", isCritical ? 1.5 : 1)
      .attr("stroke-dasharray", "3 4")
      .attr("opacity", isCritical ? 0.7 : 0.45);

    // Wide invisible click zone
    spikeG.append("rect")
      .attr("x", x - 10).attr("y", 0)
      .attr("width", 20).attr("height", innerH)
      .attr("fill", "transparent")
      .style("cursor", "pointer")
      .on("click", event => { event.stopPropagation(); onSpikeClick(spike); });

    // Glow dot
    spikeG.append("circle")
      .attr("cx", x).attr("cy", dotY)
      .attr("r", isCritical ? 7 : 5)
      .attr("fill", spikeColor)
      .attr("filter", isCritical ? "url(#critical-glow)" : "url(#spike-glow)")
      .style("cursor", "pointer")
      .on("click", event => { event.stopPropagation(); onSpikeClick(spike); });

    // Label: cluster acronym + z-score (critical only)
    if (isCritical) {
      spikeG.append("text")
        .attr("x", x + 9).attr("y", dotY - 9)
        .attr("fill", spikeColor)
        .style("font-size", "9px")
        .style("font-family", "monospace")
        .style("font-weight", "bold")
        .text(`z=${parseFloat(spike.z_score).toFixed(1)}`);
    }
  });

  // Legend (cluster labels, no r/ prefix)
  const legendG = svg.append("g")
    .attr("transform", `translate(${margin.left + 8}, ${height - 14})`);

  const colW = Math.floor(innerW / keys.length);
  keys.forEach((key, i) => {
    const lx = i * colW;
    const col = CLUSTER_COLORS[key] || FALLBACK_COLORS[i % FALLBACK_COLORS.length];
    legendG.append("rect")
      .attr("x", lx).attr("y", 0)
      .attr("width", 8).attr("height", 8)
      .attr("rx", 1)
      .attr("fill", col)
      .attr("fill-opacity", 0.85);
    legendG.append("text")
      .attr("x", lx + 11).attr("y", 7)
      .attr("fill", "rgba(255,255,255,0.45)")
      .style("font-size", "9px")
      .style("font-family", "monospace")
      .text(key);
  });
}

export default function StreamgraphChart({ streamData, onSpikeClick }) {
  const containerRef = useRef(null);
  const svgRef = useRef(null);
  const onSpikeClickRef = useRef(onSpikeClick);

  useEffect(() => {
    onSpikeClickRef.current = onSpikeClick;
  }, [onSpikeClick]);

  const render = useCallback(() => {
    if (!streamData?.data?.length) return;
    if (!containerRef.current || !svgRef.current) return;
    buildChart(
      containerRef.current,
      svgRef.current,
      streamData,
      (spike) => onSpikeClickRef.current?.(spike)
    );
  }, [streamData]);

  useEffect(() => {
    render();
    const observer = new ResizeObserver(() => render());
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [render]);

  return (
    <div ref={containerRef} className="w-full h-full">
      <svg ref={svgRef} style={{ display: "block", width: "100%", height: "100%" }} />
    </div>
  );
}
