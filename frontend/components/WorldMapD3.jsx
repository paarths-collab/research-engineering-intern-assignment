"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as d3 from "d3";
import { feature } from "topojson-client";

const TOPOJSON_URL = "https://unpkg.com/world-atlas@2/countries-110m.json";

function radiusFromImpact(impact) {
  const score = Number.isFinite(impact) ? impact : 0.25;
  return 3 + score * 8;
}

export default function WorldMapD3({ pins, selectedId, onPinClick, onDblClick }) {
  const svgRef = useRef(null);
  const wrapperRef = useRef(null);
  const [size, setSize] = useState({ width: 1280, height: 720 });
  const [worldGeo, setWorldGeo] = useState(null);
  const [mapLoadState, setMapLoadState] = useState("loading");

  useEffect(() => {
    let active = true;

    fetch(TOPOJSON_URL)
      .then((r) => (r.ok ? r.json() : null))
      .then((topology) => {
        if (!active || !topology?.objects?.countries) return;
        const geo = feature(topology, topology.objects.countries);
        setWorldGeo(geo);
        setMapLoadState("ready");
      })
      .catch(() => {
        setWorldGeo(null);
        setMapLoadState("fallback");
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!wrapperRef.current) return;

    const updateSize = () => {
      const rect = wrapperRef.current.getBoundingClientRect();
      setSize({
        width: Math.max(480, Math.floor(rect.width)),
        height: Math.max(320, Math.floor(rect.height)),
      });
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(wrapperRef.current);

    return () => observer.disconnect();
  }, []);

  const projection = useMemo(() => {
    const p = d3.geoNaturalEarth1();
    p.fitSize([size.width, size.height], { type: "Sphere" });
    return p;
  }, [size.width, size.height]);

  const path = useMemo(() => d3.geoPath(projection), [projection]);

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    svg
      .attr("viewBox", `0 0 ${size.width} ${size.height}`)
      .attr("preserveAspectRatio", "xMidYMid meet")
      .style("width", "100%")
      .style("height", "100%")
      .style("display", "block")
      .style("background", "#030302");

    svg
      .append("rect")
      .attr("width", size.width)
      .attr("height", size.height)
      .attr("fill", "url(#sea-gradient)");

    const defs = svg.append("defs");

    const glow = defs.append("filter").attr("id", "pin-glow").attr("x", "-200%").attr("y", "-200%").attr("width", "400%").attr("height", "400%");
    glow.append("feGaussianBlur").attr("stdDeviation", 3.4).attr("result", "blur");
    glow.append("feMerge").selectAll("feMergeNode").data(["blur", "SourceGraphic"]).join("feMergeNode").attr("in", (d) => d);

    const selectedGlow = defs.append("filter").attr("id", "pin-selected-glow").attr("x", "-240%").attr("y", "-240%").attr("width", "480%").attr("height", "480%");
    selectedGlow.append("feGaussianBlur").attr("stdDeviation", 5.2).attr("result", "blur");
    selectedGlow.append("feMerge").selectAll("feMergeNode").data(["blur", "SourceGraphic"]).join("feMergeNode").attr("in", (d) => d);

    const seaGradient = defs.append("linearGradient").attr("id", "sea-gradient").attr("x1", "0%").attr("x2", "0%").attr("y1", "0%").attr("y2", "100%");
    seaGradient.append("stop").attr("offset", "0%").attr("stop-color", "#040302");
    seaGradient.append("stop").attr("offset", "100%").attr("stop-color", "#080603");

    const pinGradient = defs.append("radialGradient").attr("id", "pin-gradient");
    pinGradient.append("stop").attr("offset", "0%").attr("stop-color", "#FFE08A");
    pinGradient.append("stop").attr("offset", "55%").attr("stop-color", "#FFB800");
    pinGradient.append("stop").attr("offset", "100%").attr("stop-color", "#B16C00");

    const selectedPinGradient = defs.append("radialGradient").attr("id", "pin-selected-gradient");
    selectedPinGradient.append("stop").attr("offset", "0%").attr("stop-color", "#FFFCE6");
    selectedPinGradient.append("stop").attr("offset", "60%").attr("stop-color", "#FFE08A");
    selectedPinGradient.append("stop").attr("offset", "100%").attr("stop-color", "#FFB800");

    const zoomRoot = svg.append("g").attr("class", "zoom-root");

    const fallbackSphere = { type: "Sphere" };
    const graticule = d3.geoGraticule10();

    zoomRoot
      .append("path")
      .datum(fallbackSphere)
      .attr("d", path)
      .attr("fill", "#0a0704")
      .attr("stroke", "rgba(255,190,40,0.22)")
      .attr("stroke-width", 0.9)
      .attr("vector-effect", "non-scaling-stroke");

    zoomRoot
      .append("path")
      .datum(graticule)
      .attr("d", path)
      .attr("fill", "none")
      .attr("stroke", "rgba(255,184,0,0.18)")
      .attr("stroke-width", 0.5)
      .attr("vector-effect", "non-scaling-stroke");

    if (worldGeo) {
      zoomRoot
        .append("g")
        .selectAll("path")
        .data(worldGeo.features)
        .join("path")
        .attr("d", path)
        .attr("fill", "#0d0904")
        .attr("stroke", "rgba(255,190,40,0.34)")
        .attr("stroke-width", 0.65)
        .attr("vector-effect", "non-scaling-stroke");
    }

    const statusText = mapLoadState === "loading"
      ? "Loading world map..."
      : mapLoadState === "fallback"
        ? "Map fallback active (network/topology unavailable)"
        : "";

    if (statusText) {
      svg
        .append("text")
        .attr("x", 16)
        .attr("y", 24)
        .attr("fill", "rgba(255,214,120,0.9)")
        .attr("font-size", 11)
        .attr("font-family", "monospace")
        .text(statusText);
    }

    const pinLayer = zoomRoot.append("g").attr("class", "pin-layer");

    const mappedPins = (pins || [])
      .map((pin) => {
        const coords = projection([Number(pin.lon), Number(pin.lat)]);
        if (!coords || Number.isNaN(coords[0]) || Number.isNaN(coords[1])) return null;
        return { pin, x: coords[0], y: coords[1] };
      })
      .filter(Boolean);

    const haloSelection = pinLayer
      .selectAll("circle.pin-halo")
      .data(mappedPins)
      .join("circle")
      .attr("class", "pin-halo")
      .attr("cx", (d) => d.x)
      .attr("cy", (d) => d.y)
      .attr("r", (d) => {
        const isSelected = (d.pin.event_id || d.pin.id) === selectedId;
        const base = radiusFromImpact(d.pin.impact_score);
        return isSelected ? base + 12 : base + 8;
      })
      .attr("fill", (d) => ((d.pin.event_id || d.pin.id) === selectedId ? "rgba(255,224,138,0.5)" : "rgba(255,184,0,0.3)"))
      .attr("filter", (d) => ((d.pin.event_id || d.pin.id) === selectedId ? "url(#pin-selected-glow)" : "url(#pin-glow)"))
      .style("pointer-events", "none");

    haloSelection
      .transition()
      .duration(1200)
      .ease(d3.easeSinInOut)
      .attr("opacity", 0.55)
      .transition()
      .duration(1200)
      .ease(d3.easeSinInOut)
      .attr("opacity", 0.9)
      .on("end", function repeat() {
        d3.select(this)
          .transition()
          .duration(1200)
          .ease(d3.easeSinInOut)
          .attr("opacity", 0.55)
          .transition()
          .duration(1200)
          .ease(d3.easeSinInOut)
          .attr("opacity", 0.9)
          .on("end", repeat);
      });

    pinLayer
      .selectAll("circle")
      .data(mappedPins)
      .join("circle")
      .attr("cx", (d) => d.x)
      .attr("cy", (d) => d.y)
      .attr("r", (d) => {
        const isSelected = (d.pin.event_id || d.pin.id) === selectedId;
        const base = radiusFromImpact(d.pin.impact_score);
        return isSelected ? base + 2.5 : base;
      })
      .attr("fill", (d) => ((d.pin.event_id || d.pin.id) === selectedId ? "url(#pin-selected-gradient)" : "url(#pin-gradient)"))
      .attr("stroke", (d) => ((d.pin.event_id || d.pin.id) === selectedId ? "rgba(255,255,255,0.9)" : "rgba(255,218,120,0.85)"))
      .attr("stroke-width", 1.4)
      .attr("filter", (d) => ((d.pin.event_id || d.pin.id) === selectedId ? "url(#pin-selected-glow)" : "url(#pin-glow)"))
      .style("cursor", "pointer")
      .on("click", (_, d) => onPinClick?.(d.pin));

    pinLayer
      .selectAll("text")
      .data(mappedPins)
      .join("text")
      .attr("x", (d) => d.x + 8)
      .attr("y", (d) => d.y - 8)
      .text((d) => d.pin.title || "Event")
      .attr("fill", "#FFE6A8")
      .attr("font-size", 10.5)
      .attr("font-family", "monospace")
      .attr("paint-order", "stroke")
      .attr("stroke", "rgba(0,0,0,0.85)")
      .attr("stroke-width", 3.2)
      .attr("stroke-linejoin", "round")
      .style("pointer-events", "none");

    const zoomBehavior = d3
      .zoom()
      .scaleExtent([1, 7])
      .translateExtent([
        [-size.width * 0.6, -size.height * 0.6],
        [size.width * 1.6, size.height * 1.6],
      ])
      .on("zoom", (event) => {
        zoomRoot.attr("transform", event.transform);
      });

    svg.call(zoomBehavior);
    svg.on("dblclick.zoom", null);

    if (onDblClick) {
      svg.on("dblclick", (event) => {
        if (event.target?.tagName === "svg") {
          onDblClick();
        }
      });
    }
  }, [pins, selectedId, onPinClick, onDblClick, path, projection, size.height, size.width, worldGeo, mapLoadState]);

  return (
    <div ref={wrapperRef} className="absolute inset-0">
      <svg ref={svgRef} />
    </div>
  );
}
