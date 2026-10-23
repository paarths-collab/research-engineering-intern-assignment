// The operator credential lives only in this page's memory and is lost on reload.
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
  if (work) {
    const origin = globalThis.location?.origin;
    const target = new URL(input, origin || 'http://localhost');
    const trusted = [origin, process.env.NEXT_PUBLIC_API_URL, process.env.NEXT_PUBLIC_API_BASE_URL]
      .filter(Boolean).map((value) => new URL(value).origin);
    if (!trusted.includes(target.origin) || !target.pathname.startsWith('/api/')) {
      throw new Error('Operator requests require the same-origin API or a configured backend origin.');
    }
    if (!operatorToken) throw new Error('Open Operator access and enter the server token to run analysis or collection.');
    const headers = new Headers(init.headers);
    headers.set('Authorization', `Bearer ${operatorToken}`);
    requestInit = { ...init, headers, credentials: 'omit', redirect: 'error' };
  }
  const response = await fetch(input, requestInit);
  if (!response.ok) {
    if (work && response.status === 401) setOperatorToken('');
    let detail;
    try { detail = (await response.clone().json()).detail; } catch { /* non-JSON proxy response */ }
    if (Array.isArray(detail)) detail = detail.map((item) => item.msg).join('; ');
    const error = new Error(typeof detail === 'string' ? detail : `API request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return response;
}
