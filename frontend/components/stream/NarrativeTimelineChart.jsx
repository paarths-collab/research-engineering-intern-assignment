"use client";
import { useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";

const LINE_COLOR = "#00E5FF";

function buildChart(container, svgEl, volumeData, onDateClick) {
  const rect   = container.getBoundingClientRect();
  const width  = rect.width;
  const height = rect.height;
  if (width < 10 || height < 10) return;

  const margin = { top: 28, right: 28, bottom: 48, left: 52 };
  const innerW = width  - margin.left  - margin.right;
  const innerH = height - margin.top   - margin.bottom;

  d3.select(svgEl).selectAll("*").remove();

  const svg = d3.select(svgEl)
    .attr("width",  width)
    .attr("height", height)
    .style("cursor", "crosshair");

  const defs = svg.append("defs");

  // Area gradient
  const areaGrad = defs.append("linearGradient")
    .attr("id", "area-grad").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 1);
  areaGrad.append("stop").attr("offset", "0%").attr("stop-color", LINE_COLOR).attr("stop-opacity", 0.18);
  areaGrad.append("stop").attr("offset", "100%").attr("stop-color", LINE_COLOR).attr("stop-opacity", 0);

  // Line glow
  const glow = defs.append("filter").attr("id", "line-glow")
    .attr("x", "-30%").attr("y", "-30%").attr("width", "160%").attr("height", "160%");
  glow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "3").attr("result", "blur");
  const fm = glow.append("feMerge");
  fm.append("feMergeNode").attr("in", "blur");
  fm.append("feMergeNode").attr("in", "SourceGraphic");

  // Spike glow
  const sGlow = defs.append("filter").attr("id", "spike-glow")
    .attr("x", "-100%").attr("y", "-100%").attr("width", "300%").attr("height", "300%");
  sGlow.append("feGaussianBlur").attr("in", "SourceGraphic").attr("stdDeviation", "5").attr("result", "blur");
  const sfm = sGlow.append("feMerge");
  sfm.append("feMergeNode").attr("in", "blur");
  sfm.append("feMergeNode").attr("in", "SourceGraphic");

  const g = svg.append("g")
    .attr("transform", `translate(${margin.left},${margin.top})`);

  // Aggregate total daily volume across all subreddits
  const { series, spikes } = volumeData;
  const subreddits = Object.keys(series);
  const allDates   = Array.from(
    new Set(subreddits.flatMap(s => series[s].map(d => d.date)))
  ).sort();

  const parsed = allDates.map(dateStr => {
    let topHeadline = "";
    const total = subreddits.reduce((sum, s) => {
      const pt = series[s].find(d => d.date === dateStr);
      if (pt && pt.top_headline && !topHeadline) {
        topHeadline = pt.top_headline;
      }
      return sum + (pt ? pt.count : 0);
    }, 0);
    return { date: new Date(dateStr), total, headline: topHeadline };
  });

  if (parsed.length < 2) return;

  const xScale = d3.scaleTime()
    .domain(d3.extent(parsed, d => d.date))
    .range([0, innerW]);

  const yMax = d3.max(parsed, d => d.total) || 1;
  const yScale = d3.scaleLinear()
    .domain([0, yMax * 1.1])
    .range([innerH, 0])
    .nice();

  // Background grid
  g.append("g").call(
    d3.axisLeft(yScale).ticks(5).tickSize(-innerW).tickFormat("")
  ).call(ax => {
    ax.select(".domain").remove();
    ax.selectAll("line")
      .attr("stroke", "rgba(0,229,255,0.05)")
      .attr("stroke-dasharray", "2 6");
  });

  // Area fill under the single line
  const areaGen = d3.area()
    .x(d => xScale(d.date))
    .y0(innerH)
    .y1(d => yScale(d.total))
    .curve(d3.curveCatmullRom);

  g.append("path")
    .datum(parsed)
    .attr("fill", "url(#area-grad)")
    .attr("d", areaGen);

  // Single aggregated line
  const lineGen = d3.line()
    .x(d => xScale(d.date))
    .y(d => yScale(d.total))
    .curve(d3.curveCatmullRom);

  g.append("path")
    .datum(parsed)
    .attr("fill", "none")
    .attr("stroke", LINE_COLOR)
    .attr("stroke-width", 2)
    .attr("filter", "url(#line-glow)")
    .attr("d", lineGen);

  // X axis
  g.append("g")
    .attr("transform", `translate(0,${innerH})`)
    .call(d3.axisBottom(xScale).ticks(8).tickFormat(d3.timeFormat("%b '%y")))
    .call(ax => {
      ax.select(".domain").attr("stroke", "rgba(0,229,255,0.15)");
      ax.selectAll("line").attr("stroke", "rgba(0,229,255,0.1)");
      ax.selectAll("text")
        .attr("fill", "rgba(0,229,255,0.5)")
        .style("font-size", "10px")
        .style("font-family", "monospace")
        .attr("dy", "1.2em");
    });

  // Y axis
  g.append("g")
    .call(d3.axisLeft(yScale).ticks(5).tickFormat(d => d))
    .call(ax => {
      ax.select(".domain").attr("stroke", "rgba(0,229,255,0.1)");
      ax.selectAll("line").attr("stroke", "rgba(0,229,255,0.1)");
      ax.selectAll("text")
        .attr("fill", "rgba(0,229,255,0.4)")
        .style("font-size", "9px")
        .style("font-family", "monospace");
    });

  // Spike markers (pre-computed z-score anomalies)
  const spikeList = spikes || [];
  const spikeG    = g.append("g");

  spikeList.forEach(sp => {
    const x = xScale(new Date(sp.date));
    if (isNaN(x)) return;
    const isCritical = (sp.post_count || 0) >= 100;
    const col = isCritical ? "#FF4081" : "#FFB800";

    spikeG.append("line")
      .attr("x1", x).attr("y1", 0).attr("x2", x).attr("y2", innerH)
      .attr("stroke", col)
      .attr("stroke-width", isCritical ? 1.5 : 0.8)
      .attr("stroke-dasharray", "3 5")
      .attr("opacity", isCritical ? 0.6 : 0.35);

    spikeG.append("circle")
      .attr("cx", x).attr("cy", 10)
      .attr("r",  isCritical ? 5 : 3.5)
      .attr("fill", col)
      .attr("filter", "url(#spike-glow)");
  });

  // Hover crosshair + click capture overlay
  const overlay = g.append("rect")
    .attr("width",  innerW)
    .attr("height", innerH)
    .attr("fill",   "transparent");

  const crossV = g.append("line")
    .attr("y1", 0).attr("y2", innerH)
    .attr("stroke", "rgba(0,229,255,0.6)")
    .attr("stroke-width", 1)
    .attr("stroke-dasharray", "4 4")
    .attr("opacity", 0)
    .attr("pointer-events", "none");

  // Tooltip group: date line + posts line
  const tooltipG = g.append("g").attr("pointer-events", "none").attr("opacity", 0);

  const tooltipBg = tooltipG.append("rect")
    .attr("y", -26)
    .attr("rx", 4)
    .attr("fill", "rgba(5,7,10,0.92)")
    .attr("stroke", "rgba(0,229,255,0.4)")
    .attr("stroke-width", 0.5);

  const tooltipDate = tooltipG.append("text")
    .attr("y", -12)
    .style("font-size", "10px")
    .style("font-family", "monospace")
    .attr("fill", "#00E5FF");

  const tooltipPosts = tooltipG.append("text")
    .attr("y", 2)
    .style("font-size", "10px")
    .style("font-family", "monospace")
    .attr("fill", "rgba(255,255,255,0.75)");

  const tooltipHeadline = tooltipG.append("text")
    .attr("y", 18)
    .style("font-size", "10px")
    .style("font-family", "monospace")
    .style("font-style", "italic")
    .attr("fill", "#FFD700");

  // bisector for snapping to nearest data point
  const bisect = d3.bisector(d => d.date).left;

  overlay
    .on("mousemove", function (event) {
      const [mx] = d3.pointer(event, this);
      const hoverDate = xScale.invert(mx);

      // snap to nearest data point
      const idx   = bisect(parsed, hoverDate, 1);
      const left  = parsed[idx - 1];
      const right = parsed[idx] || left;
      const nearest = hoverDate - left.date < right.date - hoverDate ? left : right;
      const sx = xScale(nearest.date);

      crossV.attr("x1", sx).attr("x2", sx).attr("opacity", 0.7);

      const dateStr  = d3.timeFormat("%b %d, %Y")(nearest.date);
      const postsTxt = `${nearest.total.toLocaleString()} posts`;

      tooltipDate.text(dateStr);
      tooltipPosts.text(postsTxt);
      tooltipHeadline.text(nearest.headline ? `"${nearest.headline}"` : "");

      // measure text widths to size the background rect
      const dw = dateStr.length  * 6.2;
      const pw = postsTxt.length * 6.2;
      const hw = nearest.headline ? (nearest.headline.length + 2) * 6.2 : 0;
      const tw = Math.max(dw, pw, hw) + 16;
      const th = nearest.headline ? 54 : 34;

      // flip tooltip to the left when near right edge
      const flipLeft = sx + tw + 8 > innerW;
      const tx = flipLeft ? sx - tw - 8 : sx + 8;

      tooltipG.attr("transform", `translate(${tx}, 18)`).attr("opacity", 1);
      tooltipBg.attr("width", tw).attr("height", th);
      tooltipDate.attr("x", 8);
      tooltipPosts.attr("x", 8);
      tooltipHeadline.attr("x", 8);
    })
    .on("mouseleave", () => {
      crossV.attr("opacity", 0);
      tooltipG.attr("opacity", 0);
    })
    .on("click", function (event) {
      const [mx] = d3.pointer(event, this);
      const clickedDate = xScale.invert(mx);
      const dateStr = d3.timeFormat("%Y-%m-%d")(clickedDate);
      onDateClick(dateStr);
    });

  // Legend label — single aggregate line
  svg.append("text")
    .attr("x", margin.left + 4)
    .attr("y", height - 16)
    .attr("fill", "rgba(0,229,255,0.4)")
    .style("font-size", "9px")
    .style("font-family", "monospace")
    .text("Total daily posts · all 10 subreddits combined");
}

export default function NarrativeTimelineChart({ volumeData, onDateClick }) {
  const containerRef   = useRef(null);
  const svgRef         = useRef(null);
  const onDateClickRef = useRef(onDateClick);

  useEffect(() => {
    onDateClickRef.current = onDateClick;
  }, [onDateClick]);

  const render = useCallback(() => {
    if (!volumeData?.series) return;
    if (!containerRef.current || !svgRef.current) return;
    buildChart(
      containerRef.current,
      svgRef.current,
      volumeData,
      (date) => onDateClickRef.current?.(date)
    );
  }, [volumeData]);

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
