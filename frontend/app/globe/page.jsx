"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";

const Globe = dynamic(() => import("react-globe.gl"), {
  ssr: false,
  loading: () => (
    <div className="w-full h-full flex items-center justify-center" style={{ background: "#0a0806" }}>
      <span
        style={{
          color: "#FFB800",
          fontFamily: "monospace",
          fontSize: 11,
          letterSpacing: "0.2em",
          opacity: 0.7,
        }}
      >
        INITIALISING GLOBAL FEED
      </span>
    </div>
  ),
});

const PANEL = {
  background: "rgba(10, 8, 6, 0.42)",
  backdropFilter: "blur(20px)",
  border: "1px solid rgba(255, 184, 0, 0.1)",
  borderRadius: "0px",
};

const INNER = {
  background: "rgba(0, 0, 0, 0.25)",
  border: "1px solid rgba(255, 255, 255, 0.04)",
  borderRadius: "0px",
};

const STATUS_COLORS = {
  running: "#FFB800",
  complete: "#4ade80",
  failed: "#FF4500",
  idle: "rgba(255,255,255,0.45)",
};

class HttpError extends Error {
  constructor(status, body) {
    super(body || `Request failed with ${status}`);
    this.name = "HttpError";
    this.status = status;
    this.body = body;
  }
}

class TimeoutError extends Error {
  constructor(message = "Request timed out") {
    super(message);
    this.name = "TimeoutError";
  }
}

function isAbortLikeError(err) {
  return (
    err?.name === "AbortError" ||
    err?.name === "TimeoutError" ||
    /aborted|timed out/i.test(String(err?.message || ""))
  );
}

function apiUrl(path) {
  const base = (process.env.NEXT_PUBLIC_API_BASE_URL || "").trim().replace(/\/$/, "");
  if (!base) return path;

  const normalizedPath = String(path || "").startsWith("/") ? String(path) : `/${String(path || "")}`;

  // Prevent accidental double /api/api/... when NEXT_PUBLIC_API_BASE_URL already includes /api.
  if (base.endsWith("/api") && normalizedPath.startsWith("/api/")) {
    return `${base}${normalizedPath.slice(4)}`;
  }

  return `${base}${normalizedPath}`;
}

async function fetchJson(path, options = {}, timeoutMs = 20000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), timeoutMs);

  try {
    const res = await fetch(apiUrl(path), {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });

    if (!res.ok) {
      const text = await res.text();
      throw new HttpError(res.status, text);
    }

    return await res.json();
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new TimeoutError(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function cleanSentence(value) {
  const raw = String(value || "")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/\s+/g, " ")
    .trim();

  if (!raw) return "";

  return raw.replace(/^[-*\d).\s]+/, "").trim();
}

function normalizeNewsArticles(payload) {
  const rawArticles = Array.isArray(payload?.articles) ? payload.articles : [];

  if (rawArticles.length > 0) {
    const dedup = new Set();
    return rawArticles
      .map((article) => {
        const title = cleanSentence(article?.title);
        const description = cleanSentence(article?.description);
        const key = `${title}|${article?.link || ""}`;
        if (!title || dedup.has(key)) return null;
        dedup.add(key);

        return {
          ...article,
          title,
          description,
        };
      })
      .filter(Boolean);
  }

  const topicSentences = Array.isArray(payload?.topic_sentences) ? payload.topic_sentences : [];
  return topicSentences
    .map((line, idx) => {
      const title = cleanSentence(line);
      if (!title) return null;
      return {
        article_id: `topic-${idx}`,
        title,
        description: "Context synthesized from correlated Reddit and news intelligence.",
        source_name: "Narrative Context",
        link: null,
      };
    })
    .filter(Boolean);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function severityColor(riskLevel) {
  const r = String(riskLevel || "").toLowerCase();
  if (r === "high") return "#FFB800";
  if (r === "medium") return "#F59E0B";
  return "#D97706";
}

function timeAgo(ts) {
  if (!ts) return "";
  const diffMs = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function normalizePins(payload) {
  const rawPins = Array.isArray(payload?.pins)
    ? payload.pins
    : Array.isArray(payload?.events)
      ? payload.events.map((event) => {
          const loc = Array.isArray(event?.locations) ? event.locations[0] : null;
          return {
            id: event?.id,
            event_id: event?.event_id || event?.id,
            lat: loc?.lat,
            lon: loc?.lon,
            location: loc?.name || event?.location,
            name: loc?.name || event?.location,
            title: event?.title,
            risk_level: event?.risk_level,
            sentiment: event?.sentiment,
            impact_score: event?.impact_score,
            timestamp: event?.timestamp || event?.last_updated,
            summary: event?.summary,
            subreddit: event?.subreddit,
          };
        })
      : [];
  return rawPins
    .map((pin, idx) => {
      const lat = Number(pin.lat);
      const lon = Number(pin.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;

      const summary = Array.isArray(pin.summary)
        ? pin.summary.join(" ")
        : String(pin.summary || "");

      return {
        id: pin.id || pin.event_id || `pin-${idx}`,
        event_id: pin.event_id || pin.id || `pin-${idx}`,
        lat,
        lon,
        location: pin.location || pin.name || "Unknown location",
        title: pin.title || "Untitled event",
        risk_level: pin.risk_level || "Low",
        sentiment: pin.sentiment || "neutral",
        impact_score: Number(pin.impact_score || 0),
        timestamp: pin.timestamp || payload?.generated_at || null,
        summary,
        subreddit: pin.subreddit || "",
      };
    })
    .filter(Boolean);
}

function buildPinElement(pin, onClick) {
  const root = document.createElement("button");
  root.type = "button";
  root.title = pin.title;
  root.style.pointerEvents = "auto";
  root.style.cursor = "pointer";
  root.style.background = "transparent";
  root.style.border = "none";
  root.style.padding = "0";
  root.style.transform = "translate(-50%, -100%)";
  root.style.display = "flex";
  root.style.alignItems = "center";
  root.style.justifyContent = "center";

  const color = severityColor(pin.risk_level);

  const pinHead = document.createElement("span");
  pinHead.style.width = "14px";
  pinHead.style.height = "14px";
  pinHead.style.borderRadius = "9999px";
  pinHead.style.border = `2px solid ${color}`;
  pinHead.style.background = "#140f08";
  pinHead.style.boxShadow = `0 0 8px ${color}`;

  const pinTail = document.createElement("span");
  pinTail.style.position = "absolute";
  pinTail.style.top = "11px";
  pinTail.style.width = "0";
  pinTail.style.height = "0";
  pinTail.style.borderLeft = "5px solid transparent";
  pinTail.style.borderRight = "5px solid transparent";
  pinTail.style.borderTop = `8px solid ${color}`;
  pinTail.style.filter = "drop-shadow(0 0 4px rgba(255,184,0,0.45))";

  root.appendChild(pinHead);
  root.appendChild(pinTail);
  root.onclick = () => onClick(pin);

  return root;
}

export default function GlobePage() {
  const globeRef = useRef(null);
  const wrapRef = useRef(null);
  const selectedRef = useRef(null);

  const [viewport, setViewport] = useState({ w: 900, h: 700 });
  const [pins, setPins] = useState([]);
  const [selected, _setSelected] = useState(null);
  // Keep a ref in sync so fetchPins can read selected without being a dep
  const setSelected = (val) => {
    selectedRef.current = val;
    _setSelected(val);
  };
  const [news, setNews] = useState([]);
  const [globeReady, setGlobeReady] = useState(false);
  const [loadingPins, setLoadingPins] = useState(true);
  const [loadingNews, setLoadingNews] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");
  const [pipelineState, setPipelineState] = useState({ status: "idle", message: "" });
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState("");
  const [analyzingEvent, setAnalyzingEvent] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState(null);

  const fetchPins = useCallback(async () => {
    setLoadingPins(true);
    setErrorMsg("");
    const startTime = Date.now();

    try {
      const data = await fetchJson("/api/globe/events/map", { method: "GET" }, 30000);
      const mapped = normalizePins(data);
      if (mapped.length > 0) {
        setPins(mapped);
      }

      const cur = selectedRef.current;
      if (cur) {
        const stillThere = mapped.find((p) => p.id === cur.id);
        if (stillThere && JSON.stringify(stillThere) !== JSON.stringify(cur)) {
          setSelected(stillThere);
        }
      }
    } catch (err) {
      if (!isAbortLikeError(err)) {
        console.error("Failed to load globe pins", err);
      }
      
      const isColdStart = (Date.now() - startTime) > 5000 || (err instanceof HttpError && (err.status === 503 || err.status === 504 || err.status === 404));
      
      if (isColdStart) {
        setErrorMsg("Backend is waking up (Cold Start)... This may take 30-60 seconds on the first load.");
      } else {
        setErrorMsg(isAbortLikeError(err) ? "Request timed out while loading event locations." : "Failed to load event locations from backend.");
      }
    } finally {
      setLoadingPins(false);
    }
  }, []);

  const fetchNewsForPin = useCallback(async (pin) => {
    setLoadingNews(true);
    setNews([]);
    setErrorMsg("");

    try {
      const data = await fetchJson(
        "/api/globe/events/news",
        {
          method: "POST",
          body: JSON.stringify({
            latitude: pin.lat,
            longitude: pin.lon,
            limit: 10,
          }),
        },
        25000
      );
      setNews(normalizeNewsArticles(data));
    } catch (err) {
      if (!isAbortLikeError(err)) {
        console.error("Failed to load location news", err);
      }

      if (isAbortLikeError(err)) {
        setErrorMsg("Request timed out while loading location news.");
        setNews([]);
        return;
      }

      // Backward-compatible fallback: some backends expose event-level news analysis instead.
      if (err instanceof HttpError && err.status === 405 && pin?.event_id) {
        try {
          const fallback = await fetchJson(
            `/api/globe/events/${encodeURIComponent(pin.event_id)}/news-analysis?refresh_cache=true`,
            { method: "POST", body: JSON.stringify({}) },
            30000
          );
          const normalized = normalizeNewsArticles(fallback);
          setNews(normalized);
          if (normalized.length === 0) {
            setErrorMsg("No readable headlines were returned for this event.");
          }
          return;
        } catch (fallbackErr) {
          if (!isAbortLikeError(fallbackErr)) {
            console.error("Fallback news-analysis failed", fallbackErr);
          }
        }
      }

      setErrorMsg("Could not fetch location news from backend.");
      setNews([]);
    } finally {
      setLoadingNews(false);
    }
  }, []);

  const handlePinClick = useCallback(
    async (pin) => {
      if (selected?.id === pin.id) return; // Prevent loop if clicking same pin
      setSelected(pin);
      if (globeRef.current) {
        globeRef.current.pointOfView({ lat: pin.lat, lng: pin.lon, altitude: 1.55 }, 1000);
      }
      await fetchNewsForPin(pin);
    },
    [fetchNewsForPin, selected]
  );

  const pollPipelineUntilSettled = useCallback(async () => {
    // Increase to 150 attempts (approx 7.5 minutes) for deep production pipelines
    for (let i = 0; i < 150; i += 1) {
      try {
        const status = await fetchJson("/api/globe/pipeline/status", { method: "GET" }, 12000);
        const nextStatus = String(status?.status || "idle").toLowerCase();
        const nextMessage = status?.error || status?.message || "";
        setPipelineState({ status: nextStatus, message: nextMessage });

        if (["complete", "failed", "idle"].includes(nextStatus)) {
          return nextStatus;
        }
      } catch (err) {
        if (!isAbortLikeError(err)) {
          console.error("Pipeline status polling failed", err);
        }
      }
      await sleep(3000);
    }
    return "running";
  }, []);

  const refreshFromPipeline = useCallback(async () => {
    setRefreshing(true);
    setPipelineState({ status: "running", message: "Starting refresh pipeline..." });
    setErrorMsg("");

    try {
      const trigger = await fetchJson("/api/globe/pipeline/run", { method: "POST", body: JSON.stringify({}) }, 15000);
      const startedState = String(trigger?.status || "running").toLowerCase();
      setPipelineState({
        status: startedState,
        message: trigger?.message || (startedState === "running" ? "Pipeline running" : ""),
      });

      const finalStatus = await pollPipelineUntilSettled();
      if (finalStatus === "complete" || finalStatus === "idle") {
        await fetchPins();
        if (selected) {
          const updatedPin = pins.find((p) => p.id === selected.id) || selected;
          await fetchNewsForPin(updatedPin);
        }
        setLastRefresh(new Date().toISOString());
      }
    } catch (err) {
      if (!isAbortLikeError(err)) {
        console.error("Pipeline refresh failed", err);
      }
      setPipelineState({ status: "failed", message: isAbortLikeError(err) ? "Pipeline request timed out." : "Pipeline trigger failed." });
      setErrorMsg(isAbortLikeError(err) ? "Pipeline request timed out. Try again." : "Could not refresh pipeline. Ensure backend service is reachable.");
    } finally {
      setRefreshing(false);
    }
  }, [fetchPins, fetchNewsForPin, pins, pollPipelineUntilSettled, selected]);

  const handleAnalyzeEvent = useCallback(async () => {
    if (!selected) return;
    setAnalyzingEvent(true);
    setAiAnalysis(null);
    setErrorMsg("");

    try {
      const data = await fetchJson(
        `/api/globe/events/${encodeURIComponent(selected.id)}/analyze?refresh_cache=true`,
        { method: "POST", body: JSON.stringify({}) },
        60000
      );
      setAiAnalysis(data.analysis_report || "No analysis generated.");
    } catch (err) {
      if (!isAbortLikeError(err)) {
        console.error("AI Analysis failed", err);
      }
      setErrorMsg(isAbortLikeError(err) ? "AI analysis request timed out. Try again." : "Failed to generate AI analysis. Check backend logs.");
    } finally {
      setAnalyzingEvent(false);
    }
  }, [selected]);

  useEffect(() => {
    fetchPins();
    
    // Background polling: Refresh pins every 2 minutes to reflect external updates
    const interval = setInterval(fetchPins, 120000);
    return () => clearInterval(interval);
  }, [fetchPins]);

  useEffect(() => {
    const updateSize = () => {
      if (!wrapRef.current) return;
      const rect = wrapRef.current.getBoundingClientRect();
      setViewport({ w: Math.floor(rect.width), h: Math.floor(rect.height) });
    };

    updateSize();
    const ro = new ResizeObserver(updateSize);
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  const onGlobeReady = useCallback(() => {
    setGlobeReady(true);
    const globe = globeRef.current;
    if (!globe) return;

    globe.controls().autoRotate = true;
    globe.controls().autoRotateSpeed = 0.42;
    globe.controls().enableDamping = true;
    globe.controls().dampingFactor = 0.08;
    globe.controls().minDistance = 150;
    globe.controls().maxDistance = 650;
    globe.pointOfView({ lat: 20, lng: 15, altitude: 2.2 }, 0);
  }, []);

  const rings = useMemo(() => {
    if (!selected) return [];
    return [{ lat: selected.lat, lng: selected.lon, maxR: 6.5, propagationSpeed: 1.35, repeatPeriod: 750 }];
  }, [selected]);

  const renderPinElement = useCallback(
    (pin) => buildPinElement(pin, handlePinClick),
    [handlePinClick]
  );

  const globeView = useMemo(
    () => (
      <Globe
        ref={globeRef}
        width={viewport.w}
        height={viewport.h}
        backgroundColor="rgba(0,0,0,0)"
        backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        atmosphereColor="#FFB800"
        atmosphereAltitude={0.1}
        htmlElementsData={pins}
        htmlLat="lat"
        htmlLng="lon"
        htmlElement={renderPinElement}
        ringsData={rings}
        ringLat="lat"
        ringLng="lng"
        ringColor={() => ["rgba(255,184,0,0.75)", "rgba(255,184,0,0.06)"]}
        ringMaxRadius="maxR"
        ringPropagationSpeed="propagationSpeed"
        ringRepeatPeriod="repeatPeriod"
        onGlobeReady={onGlobeReady}
      />
    ),
    [viewport.w, viewport.h, pins, renderPinElement, rings, onGlobeReady]
  );

  const selectedSeverityColor = severityColor(selected?.risk_level);

  return (
    <div className="h-screen max-h-screen overflow-hidden flex flex-col text-[#e6eaf0]" style={{ background: "#0a0806" }}>
      <header className="flex-shrink-0 px-8 py-5 flex items-center justify-between border-b border-white/5 bg-black/30">
        <div className="flex items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-2 bg-gradient-to-r from-[#FFB800] to-[#8B7500] opacity-20 blur-lg animate-pulse" />
            <div className="relative h-10 w-1 bg-white" />
          </div>

          <div>
            <div className="flex items-center gap-3 mb-1">
              <span className="text-[10px] uppercase font-bold tracking-[0.4em] text-[#8B7500] font-mono">
                System.Narrative.Globe
              </span>
              <div className="h-px w-12 bg-white/10" />
              <span className="text-[10px] uppercase font-bold text-white/40 font-mono">
                Live Global Signal Network
              </span>
            </div>

            <h1 className="text-3xl font-black uppercase tracking-tighter leading-none text-white">
              Global Incident Intelligence
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div
            className="px-3 py-1 border text-[10px] uppercase tracking-[0.2em] font-mono"
            style={{
              borderColor: "rgba(255,255,255,0.16)",
              color: STATUS_COLORS[pipelineState.status] || STATUS_COLORS.idle,
              background: "rgba(255,255,255,0.03)",
            }}
          >
            {pipelineState.status || "idle"}
          </div>

          <button
            onClick={refreshFromPipeline}
            disabled={refreshing}
            className="group relative px-5 py-2.5 bg-transparent border transition-all overflow-hidden disabled:opacity-60 disabled:cursor-not-allowed"
            style={{ borderColor: "rgba(255,184,0,0.45)" }}
          >
            <div className="absolute inset-0 bg-[#FFB800] translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
            <span className="relative text-xs font-black uppercase tracking-widest text-[#FFB800] group-hover:text-black transition-colors">
              {refreshing ? "Refreshing..." : "Refresh Pipeline"}
            </span>
          </button>
        </div>
      </header>

      <main className="flex-1 min-h-0 grid grid-cols-12 gap-4 p-4">
        <section className="col-span-12 lg:col-span-8 min-h-0 flex flex-col" style={PANEL}>
          <div className="flex items-center justify-between px-4 pt-4 pb-2 flex-shrink-0">
            <div className="flex items-center gap-3">
              <div className="w-1.5 h-6 bg-[#FFB800]" style={{ boxShadow: "0 0 15px rgba(255, 184, 0, 0.32)" }} />
              <h2 className="text-[11px] font-black uppercase tracking-[0.15em] text-white/90 font-manrope">
                Geospatial Event Surface
              </h2>
            </div>

            <div className="text-[10px] uppercase tracking-[0.2em] text-white/45 font-mono">
              {pins.length} Active Pins
            </div>
          </div>

          <div ref={wrapRef} className="flex-1 min-h-0 m-2 overflow-hidden relative" style={INNER}>
            <div
              className="absolute inset-0 pointer-events-none z-[1] flex items-center justify-center"
              aria-hidden="true"
            >
              <div
                style={{
                  width: "70%",
                  height: "70%",
                  borderRadius: "9999px",
                  background:
                    "radial-gradient(circle, rgba(255,215,96,0.14) 0%, rgba(255,184,0,0.09) 36%, rgba(255,184,0,0.035) 58%, rgba(255,184,0,0.01) 72%, rgba(255,184,0,0) 82%)",
                  filter: "blur(10px)",
                }}
              />
            </div>

            {!selected && globeReady && (
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 text-[10px] tracking-[0.2em] text-[#FFB800]/60 whitespace-nowrap">
                CLICK A LOCATION PIN TO INVESTIGATE
              </div>
            )}

            {loadingPins && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/40 backdrop-blur-sm text-[11px] tracking-[0.2em] text-[#FFB800]">
                LOADING INCIDENT LOCATIONS...
              </div>
            )}

            {globeView}
          </div>
        </section>

        <aside className="col-span-12 lg:col-span-4 min-h-0 flex flex-col" style={PANEL}>
          <div className="flex items-center gap-3 px-4 pt-4 pb-2 flex-shrink-0">
            <div className="w-1.5 h-6 bg-[#FFB800]" style={{ boxShadow: "0 0 15px rgba(255, 184, 0, 0.32)" }} />
            <h2 className="text-[11px] font-black uppercase tracking-[0.15em] text-white/90">Intelligence Feed</h2>
          </div>

          <div className="flex-1 min-h-0 m-2 p-4 overflow-y-auto" style={INNER}>
            {!selected && (
              <div className="h-full flex items-center justify-center text-center text-white/45 text-xs tracking-[0.12em] leading-6">
                Select a location pin to load
                <br />
                related live news intelligence.
              </div>
            )}

            {selected && (
              <>
                <div className="mb-4 pb-3 border-b border-white/10">
                  <span
                    className="inline-block px-2 py-1 text-[9px] uppercase tracking-[0.25em] font-bold mb-2"
                    style={{
                      color: selectedSeverityColor,
                      border: `1px solid ${selectedSeverityColor}44`,
                      background: `${selectedSeverityColor}22`,
                    }}
                  >
                    RISK SIGNAL
                  </span>

                  <h3 className="text-sm text-white font-semibold leading-5 mb-2">{selected.title}</h3>

                  <div className="text-[10px] tracking-[0.12em] text-white/50 flex flex-wrap gap-x-3 gap-y-1">
                    <span>{selected.location}</span>
                    <span>{timeAgo(selected.timestamp)}</span>
                    {selected.subreddit && <span>r/{selected.subreddit}</span>}
                  </div>

                  {selected.summary && (
                    <p className="text-xs text-white/65 mt-3 leading-5">{selected.summary}</p>
                  )}
                </div>

                <div className="flex items-center justify-between mb-3">
                  <div className="text-[9px] uppercase tracking-[0.28em] text-[#FFB800]/80 font-bold">
                    Related News
                  </div>
                  <button
                    onClick={handleAnalyzeEvent}
                    disabled={analyzingEvent}
                    className="px-3 py-1 text-[9px] font-bold uppercase tracking-widest border transition-all disabled:opacity-50"
                    style={{
                      borderColor: "rgba(255,184,0,0.4)",
                      color: "#FFB800",
                      background: "rgba(255,184,0,0.1)",
                    }}
                  >
                    {analyzingEvent ? "ANALYZING..." : "AI ANALYSIS"}
                  </button>
                </div>

                {loadingNews && (
                  <div className="space-y-2">
                    {[1, 2, 3].map((i) => (
                      <div key={i} className="h-16 border border-white/10 bg-white/5 animate-pulse" />
                    ))}
                  </div>
                )}

                {!loadingNews && news.length === 0 && (
                  <div className="text-center text-white/40 text-xs leading-6 py-8">
                    No fresh articles found for this location.
                    <br />
                    Run Refresh Pipeline to fetch latest signals.
                  </div>
                )}

                {!loadingNews && news.length > 0 && (
                  <div className="space-y-2">
                    {news.map((article, idx) => (
                      <article
                        key={article.article_id || article.link || idx}
                        className="p-3 border border-white/10 bg-white/[0.03] hover:bg-[#FFB800]/[0.06] hover:border-[#FFB800]/30 transition-colors"
                      >
                        <p className="text-xs text-[#F5F0E8] leading-5 font-medium mb-1 line-clamp-2">{article.title}</p>
                        {article.description && (
                          <p className="text-[11px] text-white/55 leading-4 mb-2 line-clamp-2">{article.description}</p>
                        )}
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[10px] text-[#FFB800]/75 tracking-[0.08em] uppercase line-clamp-1">
                            {article.source_name || "Source"}
                          </span>
                          {article.link && (
                            <a
                              href={article.link}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-[10px] text-[#FFB800] tracking-[0.1em] no-underline"
                            >
                              READ →
                            </a>
                          )}
                        </div>
                      </article>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </aside>
      </main>

      <footer
        className="flex-shrink-0 border-t px-4 py-3 overflow-x-auto"
        style={{ borderColor: "rgba(255,184,0,0.15)", background: "#030201" }}
      >
        <div className="flex gap-2 min-w-max">
          {pins.map((pin) => (
            <button
              key={pin.id}
              onClick={() => handlePinClick(pin)}
              className="px-3 py-1.5 text-[10px] tracking-[0.12em] border whitespace-nowrap transition-all"
              style={{
                borderColor: selected?.id === pin.id ? severityColor(pin.risk_level) : "rgba(255,255,255,0.14)",
                color: selected?.id === pin.id ? "#FFE082" : "rgba(255,255,255,0.48)",
                background: selected?.id === pin.id ? "rgba(255,184,0,0.08)" : "transparent",
              }}
            >
              {pin.location}
            </button>
          ))}
        </div>
      </footer>

      {(errorMsg || pipelineState.message || lastRefresh) && (
        <div
          className="fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 text-[10px] uppercase tracking-[0.16em] border z-[70]"
          style={{
            borderColor: "rgba(255,184,0,0.25)",
            background: "rgba(10,8,6,0.88)",
            color: errorMsg ? "#FF4500" : "rgba(255,255,255,0.75)",
          }}
        >
          {errorMsg || pipelineState.message || (lastRefresh ? `Updated ${timeAgo(lastRefresh)}` : "")}
        </div>
      )}

      {/* AI Analysis Modal Overlay */}
      {aiAnalysis && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
          <div className="relative w-full max-w-3xl max-h-[85vh] flex flex-col bg-[#0a0806] border border-[#FFB800]/30 shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-black/40">
              <div className="flex items-center gap-3">
                <div className="w-1.5 h-6 bg-[#FFB800] shadow-[0_0_15px_rgba(255,184,0,0.32)]" />
                <h2 className="text-xs font-black uppercase tracking-[0.15em] text-[#FFB800]">
                  Tactical Intelligence Assessment
                </h2>
              </div>
              <button
                onClick={() => setAiAnalysis(null)}
                className="text-white/50 hover:text-white transition-colors"
                title="Close"
              >
                ✕
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 text-sm text-[#e6eaf0] prose prose-invert prose-p:leading-6 prose-headings:text-[#FFB800] max-w-none">
              {aiAnalysis.split("\n").map((line, i) => {
                if (line.startsWith("**") && line.endsWith("**")) {
                  return (
                    <h3 key={i} className="text-[#FFB800] font-bold uppercase tracking-wider text-xs mt-6 mb-2 border-b border-white/10 pb-1">
                      {line.replace(/\*\*/g, "")}
                    </h3>
                  );
                }
                if (line.startsWith("- ")) {
                  return <li key={i} className="ml-4 text-white/80">{line.substring(2)}</li>;
                }
                if (!line.trim()) return <br key={i} />;
                return <p key={i} className="mb-2 text-white/80">{line}</p>;
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
