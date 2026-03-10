"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import SourceDetailModal from "./SourceDetailModal";

const MOCK_DATA = {
  name: "Media Ecosystem",
  children: [
    {
      name: "News",
      children: [
        { name: "nytimes.com", loc: 120, p_sub: 0.18, p_global: 0.05, narratives: ["Election coverage", "Foreign policy", "Economic policy"] },
        { name: "cnn.com", loc: 85, p_sub: 0.12, p_global: 0.04, narratives: ["Breaking news", "Political analysis", "U.S. elections"] },
        { name: "foxnews.com", loc: 90, p_sub: 0.14, p_global: 0.04, narratives: ["Conservative viewpoints", "Immigration", "Economy"] },
        { name: "bbc.com", loc: 70, p_sub: 0.10, p_global: 0.06, narratives: ["Global news", "UK politics", "International relations"] },
        { name: "washingtonpost.com", loc: 60, p_sub: 0.09, p_global: 0.03, narratives: ["White House reporting", "Investigations", "Democracy"] },
      ],
    },
    { name: "Blogs", children: [{ name: "medium.com", loc: 30, p_sub: 0.05, p_global: 0.01, narratives: ["Tech updates", "Personal stories"] }, { name: "substack.com", loc: 45, p_sub: 0.08, p_global: 0.02, narratives: ["Independent journalism", "Opinion pieces", "Culture"] }] },
    { name: "Advocacy", children: [{ name: "eff.org", loc: 40, p_sub: 0.04, p_global: 0.001, narratives: ["Digital rights", "Privacy", "Censorship"] }, { name: "aclu.org", loc: 35, p_sub: 0.03, p_global: 0.002, narratives: ["Civil liberties", "Legal action", "Human rights"] }] },
    { name: "Research", children: [{ name: "pewresearch.org", loc: 25, p_sub: 0.03, p_global: 0.005, narratives: ["Social trends", "Demographics", "Public opinion"] }, { name: "brookings.edu", loc: 20, p_sub: 0.02, p_global: 0.004, narratives: ["Public policy", "Economics", "Governance"] }] },
    { name: "Government", children: [{ name: "whitehouse.gov", loc: 15, p_sub: 0.02, p_global: 0.002, narratives: ["Executive orders", "Press briefs", "Policy announcements"] }, { name: "cdc.gov", loc: 10, p_sub: 0.01, p_global: 0.010, narratives: ["Public health", "Guidelines", "Data"] }] },
  ],
};

const CATEGORY_COLORS = {
  News: "#FFB800",
  Blogs: "#D4AF37",
  Advocacy: "#8B7500",
  Research: "#a39171",
  Government: "#C0A000",
};

export default function PolarizeTreemap({ subreddit = "politics" }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedSource, setSelectedSource] = useState(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
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
      if (res.ok) {
        const json = await res.json();
        // Backend returns { name, children } hierarchical structure
        if (json && json.children && json.children.length > 0) {
          setData(json);
          setLoading(false);
          return;
        }
      }
    } catch (e) {
      // Fall through to mock
    }
    // Fallback: use mock but tag the sub for re-render triggering
    setData({ ...MOCK_DATA, sub });
    setLoading(false);
  }, []);

  useEffect(() => {
    if (subreddit) {
      fetchData(subreddit);
      setCurrentView("root");
      setCurrentCategory(null);
    }
  }, [subreddit, fetchData]);

  useEffect(() => {
    if (!data || !svgRef.current || dimensions.width === 0) return;
    drawTreemap();
  }, [data, dimensions, currentView, currentCategory]);

  const drawTreemap = () => {
    const { width, height: containerHeight } = dimensions;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    let displayData;
    let isUniform = true;

    if (currentView === "root") {
      displayData = {
        name: data.name,
        children: data.children.map((c) => ({
          name: c.name,
          loc: c.children.reduce((sum, child) => sum + (child.loc || 0), 0)
        }))
      };
    } else {
      const cat = data.children.find((c) => c.name === currentCategory);
      displayData = cat ? { name: cat.name, children: cat.children } : data;
    }

    const items = displayData.children || [];
    let drawHeight = containerHeight;

    // In category view, if we have many items, expand height for scrolling
    if (isUniform && items.length > 12) {
      const columns = width > 1000 ? 5 : width > 700 ? 4 : 3;
      const rows = Math.ceil(items.length / columns);
      drawHeight = Math.max(containerHeight, rows * 100);
    }

    svg.attr("width", width).attr("height", drawHeight);

    const root = d3
      .hierarchy(displayData)
      .sum((d) => (isUniform ? 1 : d.loc || 0))
      .sort((a, b) => b.value - a.value);

    // Padding increased for better separation in the uniform grid
    d3.treemap().size([width, drawHeight]).paddingInner(4).paddingOuter(0)(root);

    const cells = svg
      .selectAll("g")
      .data(root.leaves())
      .join("g")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`)
      .style("cursor", "pointer")
      .on("click", (_, d) => {
        if (currentView === "root") {
          const catName = d.data.name;
          if (catName) {
            setCurrentView("category");
            setCurrentCategory(catName);
          }
        } else {
          setSelectedSource({
            ...d.data,
            category: currentCategory
          });
          setIsModalOpen(true);
        }
      });

    cells
      .append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("fill", (d) => {
        const cat = currentView === "root" ? d.data.name : currentCategory;
        return CATEGORY_COLORS[cat] || "#FFB800";
      })
      .attr("fill-opacity", 0.6)
      .attr("stroke", "rgba(0,0,0,0.3)")
      .attr("stroke-width", 1);

    cells
      .append("title")
      .text((d) => `${d.data.name} (${d.data.loc} refs)`);

    cells
      .append("text")
      .attr("x", 10)
      .attr("y", 22)
      .attr("fill", "white")
      .attr("font-size", (d) => {
        const w = d.x1 - d.x0;
        return isUniform ? 11 : Math.max(8, Math.min(12, w / 7));
      })
      .attr("font-family", "Inter")
      .attr("font-weight", "600")
      .attr("pointer-events", "none")
      .text((d) => {
        const name = d.data.name;
        const width = d.x1 - d.x0;
        const limit = Math.floor(width / (isUniform ? 7 : 6));
        return name.length > limit ? name.slice(0, Math.max(2, limit - 1)) + "…" : name;
      });

    cells
      .filter((d) => d.y1 - d.y0 > 40)
      .append("text")
      .attr("x", 10)
      .attr("y", 38)
      .attr("fill", "rgba(255,255,255,0.4)")
      .attr("font-size", 9)
      .attr("font-family", "JetBrains Mono")
      .attr("pointer-events", "none")
      .text((d) => `${d.data.loc} REFS`);
  };

  return (
    <div className="h-full flex flex-col bg-[#0a0806]/40 font-inter">
      <div className="px-4 py-3 flex items-center justify-between border-b border-white/5 bg-black/20">
        <div className="flex items-center gap-3">
          <button
            onClick={() => { setCurrentView("root"); setCurrentCategory(null); }}
            className={`text-[10px] uppercase tracking-widest font-mono transition-colors ${currentView === "root" ? "text-[#FFB800]" : "text-white/40 hover:text-white"
              }`}
          >
            r/{subreddit}
          </button>
          {currentCategory && (
            <>
              <span className="text-white/20 font-mono text-xs">/</span>
              <span className="text-[10px] uppercase tracking-widest font-mono text-[#8B7500]">
                {currentCategory}
              </span>
            </>
          )}
        </div>

        {currentView === "category" && (
          <button
            onClick={() => { setCurrentView("root"); setCurrentCategory(null); }}
            className="text-[10px] uppercase font-bold text-[#FFB800] flex items-center gap-1 hover:underline"
          >
            ← Back to Categories
          </button>
        )}
      </div>

      <div ref={containerRef} className="flex-1 relative overflow-y-auto overflow-x-hidden scrollbar-hide">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-[10px] font-mono text-[#8B7500] animate-pulse tracking-[0.3em] uppercase">
              Mapping media clusters...
            </div>
          </div>
        ) : (
          <svg ref={svgRef} className="w-full" />
        )}
      </div>

      <SourceDetailModal
        source={selectedSource}
        isOpen={isModalOpen}
        subreddit={subreddit}
        onClose={() => setIsModalOpen(false)}
      />
    </div>
  );
}
