const API_BASE = String(process.env.NEXT_PUBLIC_API_URL || '').trim().replace(/\/$/, '');

const NEWS_CACHE_KEY = 'perspective.newsPresets.v1';
const PERSONA_CACHE_KEY = 'perspective.personaPresets.v1';

const FALLBACK_PERSONA_PRESETS = [
  { label: 'r/politics', description: 'Progressive US politics community lens.' },
  { label: 'r/PoliticalDiscussion', description: 'Policy-first analytical community lens.' },
  { label: 'r/liberal', description: 'Rights and equity-focused liberal lens.' },
  { label: 'r/progressive', description: 'Structural reform and anti-corporate lens.' },
  { label: 'r/socialdemocracy', description: 'Reformist social-democratic policy lens.' },
  { label: 'r/democrats', description: 'Institutional Democratic campaign lens.' },
  { label: 'r/AskALiberal', description: 'Explanatory liberal Q&A lens.' },
  { label: 'r/DemocraticSocialism', description: 'Class and structural critique lens.' },
  { label: 'r/Conservative', description: 'Populist conservative lens.' },
  { label: 'r/Republican', description: 'GOP governance and electoral lens.' },
  { label: 'r/AskConservatives', description: 'Principle-first conservative Q&A lens.' },
  { label: 'r/Libertarian', description: 'Liberty-first, anti-overreach lens.' },
  { label: 'r/GoldandBlack', description: 'Anarcho-capitalist and NAP-centric lens.' },
  { label: 'r/ModeratePolitics', description: 'Compromise and civility-first lens.' },
  { label: 'r/NeutralPolitics', description: 'Evidence-first, low-spin lens.' },
].map((p) => ({
  ...p,
  traits: [String(p.label).replace(/^r\//i, '').toLowerCase()],
  ideology_vector: [0.5, 0.5, 0.5, 0.5],
}));

export function getFallbackPersonaPresets() {
  return FALLBACK_PERSONA_PRESETS.map((item) => ({ ...item }));
}

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

function sanitizePersonaPresets(raw) {
  return raw
    .map((p) => {
      const label = String(p?.subreddit || p?.name || p?.label || '').trim();
      if (!label) return null;
      const prompt = String(p?.persona_prompt || p?.description || '').trim();
      return {
        label,
        description: prompt,
        traits: [label.replace(/^r\//i, '').toLowerCase()],
        ideology_vector: [0.5, 0.5, 0.5, 0.5],
      };
    })
    .filter(Boolean);
}

function getCachedPersonaPresets() {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(PERSONA_CACHE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return sanitizePersonaPresets(parsed);
  } catch {
    return [];
  }
}

function setCachedPersonaPresets(items) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PERSONA_CACHE_KEY, JSON.stringify(items));
  } catch {
    // ignore storage failures
  }
}

function buildApiCandidates() {
  const candidates = [];

  // Prefer same-origin proxy via Next.js rewrites to avoid CORS/network mismatches.
  candidates.push('');

  if (API_BASE) {
    candidates.push(API_BASE);
    if (API_BASE.includes('localhost')) {
      candidates.push(API_BASE.replace('localhost', '127.0.0.1'));
    } else if (API_BASE.includes('127.0.0.1')) {
      candidates.push(API_BASE.replace('127.0.0.1', 'localhost'));
    }
  } else {
    candidates.push('http://localhost:8000');
    candidates.push('http://127.0.0.1:8000');
  }

  return Array.from(new Set(candidates));
}

async function parseJsonResponse(response, label) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`${label} returned non-JSON response: ${text.slice(0, 180)}`);
  }
}

async function requestJson(path, init = {}, label = 'Request') {
  const candidates = buildApiCandidates();
  let lastError = null;

  for (const base of candidates) {
    const url = `${base}${path}`;
    try {
      const response = await fetch(url, init);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`${label} failed: ${response.status} ${text}`.trim());
      }
      return await parseJsonResponse(response, label);
    } catch (error) {
      lastError = error;
    }
  }

  throw new Error(`${label} failed across all API candidates. ${lastError?.message || ''}`);
}

export async function fetchPersonaPresets() {
  const cached = getCachedPersonaPresets();

  try {
    const payload = await requestJson('/api/perspective/personas', { method: 'GET' }, 'Load persona presets');
    const raw = Array.isArray(payload?.personas) ? payload.personas : [];
    const normalized = sanitizePersonaPresets(raw);
    if (normalized.length > 0) {
      setCachedPersonaPresets(normalized);
      return normalized;
    }
  } catch (error) {
    if (cached.length > 0) return cached;
  }

  if (cached.length > 0) return cached;
  return getFallbackPersonaPresets();
}

export async function fetchNewsPresets(limit = 15) {
  const cached = getCachedNewsPresets();

  try {
    const payload = await requestJson(
      `/api/perspective/news-presets?limit=${limit}`,
      { method: 'GET' },
      'Load news presets'
    );
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
  const payload = {
    nodes,
    edges,
    debate_rounds: options.debateRounds,
    options,
  };

  return requestJson(
    '/api/perspective/simulate',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
    'Simulate perspective graph'
  );
}
