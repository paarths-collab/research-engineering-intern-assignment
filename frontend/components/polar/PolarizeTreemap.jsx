"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import DomainCard from "./DomainCard";

const MOCK_DATA = {
  name: "Media Ecosystem",
  children: [
    {
      name: "News",
      children: [
        { name: "nytimes.com", loc: 120, lift: 4.5 },
        { name: "cnn.com", loc: 85, lift: 2.1 },
        { name: "bbc.com", loc: 74, lift: 1.8 },
        { name: "reuters.com", loc: 66, lift: 2.4 },
        { name: "apnews.com", loc: 52, lift: 1.6 },
      ],
    },
    {
      name: "Advocacy",
      children: [
        { name: "eff.org", loc: 40, lift: 3.2 },
        { name: "aclu.org", loc: 35, lift: 3.8 },
        { name: "hrw.org", loc: 28, lift: 2.7 },
      ],
    },
    {
      name: "Social",
      children: [
        { name: "twitter.com", loc: 98, lift: 5.1 },
        { name: "reddit.com", loc: 87, lift: 4.2 },
        { name: "facebook.com", loc: 63, lift: 3.0 },
      ],
    },
    {
      name: "Blog",
      children: [
        { name: "substack.com", loc: 45, lift: 2.9 },
        { name: "medium.com", loc: 38, lift: 2.1 },
        { name: "wordpress.com", loc: 22, lift: 1.4 },
      ],
    },
    {
      name: "Government",
      children: [
        { name: "state.gov", loc: 31, lift: 1.9 },
        { name: "congress.gov", loc: 24, lift: 1.7 },
      ],
    },
    {
      name: "Academic",
      children: [
        { name: "scholar.google.com", loc: 20, lift: 1.3 },
        { name: "jstor.org", loc: 15, lift: 1.1 },
      ],
    },
  ],
};

const CATEGORY_COLORS = {
  News: "#3b82f6",
  Advocacy: "#8b5cf6",
  Social: "#f59e0b",
  Blog: "#10b981",
  Government: "#ef4444",
  Academic: "#06b6d4",
};

const SUBREDDITS = ["politics", "worldnews", "geopolitics", "news", "conspiracy"];

export default function PolarizeTreemap() {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const [data, setData] = useState(null);
  const [selectedSubreddit, setSelectedSubreddit] = useState("politics");
  const [loading, setLoading] = useState(true);
  const [selectedDomain, setSelectedDomain] = useState(null);
  const [currentView, setCurrentView] = useState("root");
  const [currentCategory, setCurrentCategory] = useState(null);
  const [dimensions, setDimensions] = useState({ width: 600, height: 400 });

  useEffect(() => {
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  const fetchData = useCallback(async (sub) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/treemap/${sub}`);
      const json = await res.json();
      setData(json);
    } catch {
      setData(MOCK_DATA);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(selectedSubreddit);
    setCurrentView("root");
    setCurrentCategory(null);
  }, [selectedSubreddit, fetchData]);

  useEffect(() => {
    if (!data || !svgRef.current || dimensions.width === 0) return;
    drawTreemap();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, dimensions, currentView, currentCategory]);

  const drawTreemap = () => {
    const { width, height } = dimensions;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    svg.attr("width", width).attr("height", height);

    let displayData;
    if (currentView === "root") {
      displayData = data;
    } else {
      const cat = data.children.find((c) => c.name === currentCategory);
      displayData = cat
        ? { name: cat.name, children: cat.children }
        : data;
    }

    const root = d3
      .hierarchy(displayData)
      .sum((d) => d.loc || 0)
      .sort((a, b) => b.value - a.value);

    d3.treemap().size([width, height]).paddingInner(3).paddingOuter(4)(root);

    const leaves = root.leaves();

    const g = svg.append("g");

    const cells = g
      .selectAll("g")
      .data(leaves)
      .join("g")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`)
      .style("cursor", "pointer")
      .on("click", (_, d) => {
        if (currentView === "root") {
          const catName = d.parent?.data?.name;
          if (catName) {
            setCurrentView("category");
            setCurrentCategory(catName);
          }
        } else {
          setSelectedDomain({
            name: d.data.name,
            category: currentCategory || d.parent?.data?.name,
            loc: d.data.loc,
            lift: d.data.lift,
          });
        }
      })
      .on("mouseenter", function () {
        d3.select(this).select("rect").attr("opacity", 1);
        d3.select(this).select(".hover-border").attr("opacity", 1);
      })
      .on("mouseleave", function () {
        d3.select(this).select("rect").attr("opacity", 0.75);
        d3.select(this).select(".hover-border").attr("opacity", 0);
      });

    // Rect fill
    cells
      .append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("fill", (d) => {
        const cat = currentView === "root" ? d.parent?.data?.name : currentCategory;
        const base = CATEGORY_COLORS[cat] || "#3b82f6";
        return base;
      })
      .attr("opacity", 0.75)
      .attr("rx", 1);

    // Hover border
    cells
      .append("rect")
      .attr("class", "hover-border")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("fill", "none")
      .attr("stroke", "white")
      .attr("stroke-width", 1.5)
      .attr("opacity", 0)
      .attr("rx", 1);

    // Lift overlay
    cells
      .append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("fill", "black")
      .attr("opacity", (d) => {
        const lift = d.data.lift || 1;
        return Math.max(0, 0.6 - lift * 0.08);
      })
      .attr("rx", 1);

    // Category badge (root view)
    if (currentView === "root") {
      cells
        .filter((d) => d.x1 - d.x0 > 60 && d.y1 - d.y0 > 24)
        .append("text")
        .attr("x", 6)
        .attr("y", 12)
        .attr("fill", "rgba(255,255,255,0.45)")
        .attr("font-size", 8)
        .attr("font-family", "monospace")
        .attr("letter-spacing", "0.1em")
        .text((d) => (d.parent?.data?.name || "").toUpperCase());
    }

    // Domain name label
    cells
      .filter((d) => d.x1 - d.x0 > 50 && d.y1 - d.y0 > 30)
      .append("text")
      .attr("x", 6)
      .attr("y", (d) => (currentView === "root" ? 24 : 18))
      .attr("fill", "white")
      .attr("font-size", (d) => {
        const w = d.x1 - d.x0;
        return w > 100 ? 11 : 9;
      })
      .attr("font-family", "monospace")
      .attr("font-weight", "600")
      .text((d) => {
        const w = d.x1 - d.x0;
        const name = d.data.name;
        return name.length > Math.floor(w / 7) ? name.slice(0, Math.floor(w / 7)) + "…" : name;
      });

    // Lift score
    cells
      .filter((d) => d.x1 - d.x0 > 60 && d.y1 - d.y0 > 44)
      .append("text")
      .attr("x", 6)
      .attr("y", (d) => (currentView === "root" ? 38 : 32))
      .attr("fill", "rgba(255,255,255,0.6)")
      .attr("font-size", 8)
      .attr("font-family", "monospace")
      .text((d) => `LIFT ${d.data.lift?.toFixed(1) || "—"}×`);

    // LOC count
    cells
      .filter((d) => d.x1 - d.x0 > 80 && d.y1 - d.y0 > 56)
      .append("text")
      .attr("x", 6)
      .attr("y", (d) => (currentView === "root" ? 50 : 44))
      .attr("fill", "rgba(255,255,255,0.35)")
      .attr("font-size", 7)
      .attr("font-family", "monospace")
      .text((d) => `${d.data.loc} refs`);
  };

  return (
    <div className="bg-[#0c0c0e] border border-[#1f1f23] rounded-none flex flex-col h-full">
      {/* Header */}
      <div className="border-b border-[#1f1f23] px-4 py-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-mono text-[#3b82f6] tracking-[0.2em] uppercase">
            Module 03 · Primary
          </p>
          <h2 className="text-sm font-mono text-white tracking-widest uppercase mt-0.5">
            Media Ecosystem Treemap
          </h2>
        </div>

        {/* Subreddit selector */}
        <div className="flex gap-1 flex-wrap">
          {SUBREDDITS.map((sub) => (
            <button
              key={sub}
              onClick={() => setSelectedSubreddit(sub)}
              className={`text-[9px] font-mono px-2 py-1 border transition-all tracking-wider uppercase ${
                selectedSubreddit === sub
                  ? "border-[#3b82f6] text-[#3b82f6] bg-[#3b82f6]/10"
                  : "border-[#27272a] text-[#52525b] hover:border-[#3b82f6]/40 hover:text-[#71717a]"
              }`}
            >
              r/{sub}
            </button>
          ))}
        </div>
      </div>

      {/* Breadcrumb */}
      <div className="px-4 py-2 border-b border-[#111113] flex items-center gap-2">
        <button
          onClick={() => { setCurrentView("root"); setCurrentCategory(null); }}
          className={`text-[9px] font-mono transition-colors ${
            currentView === "root" ? "text-[#3b82f6]" : "text-[#52525b] hover:text-[#a1a1aa]"
          }`}
        >
          r/{selectedSubreddit}
        </button>
        {currentView === "category" && currentCategory && (
          <>
            <span className="text-[#27272a] font-mono text-[9px]">›</span>
            <span
              className="text-[9px] font-mono uppercase"
              style={{ color: CATEGORY_COLORS[currentCategory] || "#3b82f6" }}
            >
              {currentCategory}
            </span>
            <span className="text-[9px] font-mono text-[#3f3f46] ml-2">
              · Click domain for intelligence
            </span>
          </>
        )}
        {currentView === "root" && (
          <span className="text-[9px] font-mono text-[#3f3f46]">
            · Click category to drill down
          </span>
        )}
      </div>

      {/* Treemap SVG */}
      <div ref={containerRef} className="flex-1 relative min-h-0" style={{ minHeight: 300 }}>
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3">
              <div className="w-6 h-6 border border-[#3b82f6] border-t-transparent rounded-full animate-spin" />
              <p className="text-[10px] font-mono text-[#3b82f6] animate-pulse tracking-widest">
                MAPPING MEDIA ECOSYSTEM...
              </p>
            </div>
          </div>
        ) : (
          <svg ref={svgRef} className="w-full h-full" />
        )}
      </div>

      {/* Category legend */}
      <div className="border-t border-[#1f1f23] px-4 py-2 flex flex-wrap gap-3">
        {Object.entries(CATEGORY_COLORS).map(([cat, color]) => (
          <div key={cat} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-sm" style={{ background: color }} />
            <span className="text-[8px] font-mono text-[#52525b]">{cat.toUpperCase()}</span>
          </div>
        ))}
      </div>

      {/* Domain card slide-in */}
      {selectedDomain && (
        <DomainCard domain={selectedDomain} onClose={() => setSelectedDomain(null)} />
      )}
    </div>
  );
}
