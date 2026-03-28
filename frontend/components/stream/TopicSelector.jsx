"use client";
import { useState } from "react";

const GOLD = "#FFB800";

const CLUSTER_COLORS = {
  "Geopolitics": "#FFB800",
  "US Politics":  "#FF4081",
  "Economy":      "#00BCD4",
  "Technology":   "#AB47BC",
  "Culture":      "#66BB6A",
};

export default function TopicSelector({ cluster, topics, onSelect, selected }) {
  const color = CLUSTER_COLORS[cluster] || GOLD;

  if (!topics || topics.length === 0) {
    return (
      <p className="text-[10px] font-mono text-white/30 uppercase tracking-widest">
        No topics extracted for this window.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-white/30 mb-1">
        Detected Topics — Select one to analyze
      </p>
      <div className="flex flex-wrap gap-2">
        {topics.map((topic) => {
          const isActive = topic === selected;
          return (
            <button
              key={topic}
              onClick={() => onSelect(topic)}
              className="px-3 py-1.5 text-[10px] font-mono font-bold uppercase tracking-wide transition-all duration-150"
              style={{
                background:  isActive ? color : "rgba(255,255,255,0.04)",
                color:       isActive ? "#000" : color,
                border:      `1px solid ${isActive ? color : `${color}40`}`,
                boxShadow:   isActive ? `0 0 14px ${color}55` : "none",
                cursor:      "pointer",
              }}
            >
              {topic}
            </button>
          );
        })}
      </div>
    </div>
  );
}
