const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const NEWS_CACHE_KEY = 'perspective.newsPresets.v1';

function sanitizeNewsPresets(raw) {
  return raw
    .map((n) => {
      const label = String(n?.label || '').trim();
      if (!label) return null;

      return {
        label,
        description: String(n?.description || '').trim(),
        event_id: String(n?.event_id || '').trim(),
        risk_level: String(n?.risk_level || '').trim(),
        impact_score: n?.impact_score,
        strategic_implications: Array.isArray(n?.strategic_implications) ? n.strategic_implications : [],
        globe_reports: Array.isArray(n?.reports) ? n.reports : [],
      };
    })
    .filter(Boolean);
}

export function getCachedNewsPresets() {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(NEWS_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return sanitizeNewsPresets(parsed);
  } catch {
    return [];
  }
}

function setCachedNewsPresets(items) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(NEWS_CACHE_KEY, JSON.stringify(items));
  } catch {
    // ignore storage failures
  }
}

export async function fetchPersonaPresets() {
  const response = await fetch(`${API_BASE}/api/perspective/personas`);
  if (!response.ok) {
    throw new Error(`Failed to load persona presets: ${response.status}`);
  }

  const payload = await response.json();
  const raw = Array.isArray(payload?.personas) ? payload.personas : [];

  return raw
    .map((p) => {
      const label = String(p?.subreddit || p?.name || '').trim();
      const prompt = String(p?.persona_prompt || '').trim();
      if (!label) return null;
      return {
        label,
        description: prompt,
        traits: [label.replace(/^r\//i, '').toLowerCase()],
        ideology_vector: [0.5, 0.5, 0.5, 0.5],
      };
    })
    .filter(Boolean);
}

export async function fetchNewsPresets(limit = 15) {
  const cached = getCachedNewsPresets();

  try {
    const response = await fetch(`${API_BASE}/api/perspective/news-presets?limit=${limit}`);
    if (!response.ok) {
      throw new Error(`Failed to load news presets: ${response.status}`);
    }

    const payload = await response.json();
    const raw = Array.isArray(payload?.news) ? payload.news : [];
    const normalized = sanitizeNewsPresets(raw);

    if (normalized.length > 0) {
      setCachedNewsPresets(normalized);
      return normalized;
    }
  } catch (error) {
    if (cached.length > 0) {
      return cached;
    }
    throw error;
  }

  return cached;
}

export async function simulateGraph(nodes, edges, options = {}) {
  const payload = JSON.stringify({
    nodes,
    edges,
    debate_rounds: options.debateRounds,
    options,
  });

  const candidates = [API_BASE];
  if (API_BASE.includes('localhost')) {
    candidates.push(API_BASE.replace('localhost', '127.0.0.1'));
  } else if (API_BASE.includes('127.0.0.1')) {
    candidates.push(API_BASE.replace('127.0.0.1', 'localhost'));
  }

  let lastError = null;
  for (const base of candidates) {
    try {
      const response = await fetch(`${base}/api/perspective/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
      });
      if (!response.ok) throw new Error(`Simulation failed: ${await response.text()}`);
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw new Error(
    `Failed to fetch simulation API. Ensure backend is running on ${API_BASE} (or 127.0.0.1:8000). ${lastError?.message || ''}`
  );
}
