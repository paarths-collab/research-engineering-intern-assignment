import { notifyAuthRequired } from './authClient.mjs';

// Manually supplied on /admin only; never persisted or supplied to account endpoints.
let operatorToken = '';
const listeners = new Set();
export const subscribeOperatorAccess = (listener) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};
export const hasOperatorToken = () => Boolean(operatorToken);
export function setOperatorToken(value) {
  const next = String(value || '');
  if (next && (next.length < 32 || next.trim() !== next)) {
    throw new Error('Use the server operator token (at least 32 characters, without surrounding spaces).');
  }
  operatorToken = next;
  listeners.forEach((listener) => listener());
}

export async function apiFetch(input, init = {}) {
  const method = String(init.method || 'GET').toUpperCase();
  const work = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  let requestInit = init;
  let requestInput = input;
  let usingOperator = false;
  if (work) {
    const origin = globalThis.location?.origin;
    const target = new URL(input, origin || 'http://localhost');
    const trusted = [origin, process.env.NEXT_PUBLIC_API_URL, process.env.NEXT_PUBLIC_API_BASE_URL]
      .filter(Boolean).map((value) => new URL(value).origin);
    if (!trusted.includes(target.origin) || !target.pathname.startsWith('/api/') || target.username || target.password) {
      throw new Error('Analysis requests require the same-origin API or a configured backend origin.');
    }
    const headers = new Headers(init.headers);
    if (target.pathname === '/api/auth' || target.pathname.startsWith('/api/auth/')) {
      throw new Error('Use the account client for sign-in requests.');
    }
    if (operatorToken) {
      usingOperator = true;
      headers.set('Authorization', `Bearer ${operatorToken}`);
      requestInit = { ...init, headers, credentials: 'omit', redirect: 'error' };
    } else {
      // The browser session belongs to the frontend origin. Configured backend URLs
      // must pass through its API proxy so cookies never travel across origins.
      requestInput = `${target.pathname}${target.search}`;
      headers.delete('Authorization');
      headers.set('X-Narrative-CSRF', '1');
      requestInit = { ...init, headers, credentials: 'same-origin', redirect: 'error' };
    }
  }
  const response = await fetch(requestInput, requestInit);
  if (!response.ok) {
    if (work && response.status === 401) {
      if (usingOperator) setOperatorToken('');
      else notifyAuthRequired();
    }
    let detail;
    try { detail = (await response.clone().json()).detail; } catch { /* non-JSON proxy response */ }
    if (Array.isArray(detail)) detail = detail.map((item) => item.msg).join('; ');
    const message = work && response.status === 401 && !usingOperator
      ? 'Sign in to run analysis. Your session may have expired.'
      : typeof detail === 'string' ? detail : `API request failed (${response.status}).`;
    const error = new Error(message);
    error.status = response.status;
    throw error;
  }
  return response;
}
