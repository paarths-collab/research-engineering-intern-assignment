const authRequiredListeners = new Set();

export function subscribeAuthRequired(listener) {
  authRequiredListeners.add(listener);
  return () => authRequiredListeners.delete(listener);
}

export function notifyAuthRequired() {
  authRequiredListeners.forEach((listener) => listener());
}

export function safeNextPath(value, fallback = '/overview') {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) return fallback;
  let decoded;
  try { decoded = decodeURIComponent(value); } catch { return fallback; }
  if (/[\\\u0000-\u0020\u007f]/.test(decoded) || decoded.startsWith('//')) return fallback;
  const target = new URL(value, 'https://narrative.invalid');
  if (target.origin !== 'https://narrative.invalid' || /^\/(?:login|signup|admin)(?:\/|$)/.test(decodeURIComponent(target.pathname))) return fallback;
  return `${target.pathname}${target.search}${target.hash}`;
}

function authError(status, action) {
  let message = 'Account access is temporarily unavailable. Please try again later.';
  if (status === 429) message = 'Too many attempts. Please wait before trying again.';
  else if (status < 500 && action === 'login') message = 'Unable to sign in. Check your email and password.';
  else if (status < 500 && action === 'register') message = 'Unable to create this account. Check your email and use a password with 12 to 128 characters, or try signing in.';
  const error = new Error(message);
  error.status = status;
  return error;
}

async function authRequest(path, { method = 'GET', headers, body, action, signal } = {}) {
  const requestHeaders = new Headers(headers);
  if (method !== 'GET') requestHeaders.set('X-Narrative-CSRF', '1');
  // Account endpoints always use the HttpOnly session cookie, never an operator credential.
  const response = await fetch(`/api/auth/${path}`, {
    method, headers: requestHeaders, body, signal,
    credentials: 'same-origin', redirect: 'error', cache: 'no-store',
  });
  if (path === 'me' && response.status === 401) return null;
  if (!response.ok) throw authError(response.status, action);
  return response;
}

export async function getCurrentUser({ signal } = {}) {
  const response = await authRequest('me', { signal });
  return response ? response.json() : null;
}

export async function getAuthStatus({ signal } = {}) {
  const response = await authRequest('status', { signal });
  return response.json();
}

export async function signIn(email, password) {
  const body = new URLSearchParams({ username: email.trim(), password });
  await authRequest('login', {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body, action: 'login',
  });
}

export async function signUp(email, password) {
  await authRequest('register', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim(), password }), action: 'register',
  });
  await signIn(email, password);
}

export async function signOut() {
  await authRequest('logout', { method: 'POST' });
}
