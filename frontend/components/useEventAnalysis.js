"use client";

import { useCallback, useState } from "react";

export default function useEventAnalysis() {
  const [analysisById, setAnalysisById] = useState({});
  const [loadingById, setLoadingById] = useState({});
  const [errorById, setErrorById] = useState({});

  const triggerAnalysis = useCallback(async (eventId) => {
    if (!eventId) return null;
    if (analysisById[eventId]) return analysisById[eventId];

    setLoadingById((prev) => ({ ...prev, [eventId]: true }));
    setErrorById((prev) => ({ ...prev, [eventId]: null }));

    try {
      const res = await fetch(`/api/globe/events/${eventId}/analyze?max_reddit_posts=50&max_news_sources=10`, {
        method: "POST",
      });

      if (!res.ok) {
        let detail = "";
        try {
          const payload = await res.json();
          detail = payload?.detail || payload?.message || "";
        } catch {
          // ignore parse failures, fall back to status text
        }
        throw new Error(detail || `Analysis request failed (HTTP ${res.status})`);
      }

      const payload = await res.json();
      setAnalysisById((prev) => ({ ...prev, [eventId]: payload }));
      return payload;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setErrorById((prev) => ({ ...prev, [eventId]: message }));
      return null;
    } finally {
      setLoadingById((prev) => ({ ...prev, [eventId]: false }));
    }
  }, [analysisById]);

  return {
    triggerAnalysis,
    getAnalysis: (eventId) => analysisById[eventId] || null,
    isLoading: (eventId) => !!loadingById[eventId],
    getError: (eventId) => errorById[eventId] || null,
  };
}
