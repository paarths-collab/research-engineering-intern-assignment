import { dataProvenance } from './dataProvenance.mjs';

export function normalizePins(payload) {
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
        ...dataProvenance({ ...payload, ...pin }),
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

