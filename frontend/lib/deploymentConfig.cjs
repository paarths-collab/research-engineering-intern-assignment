// BACKEND_API_URL is build-time, server-side configuration. It never contains a token.
function resolveBackendOrigin(env = process.env, deploymentOrigin = '') {
  const onVercel = env.VERCEL === '1';
  const configured = String(env.BACKEND_API_URL || (onVercel ? deploymentOrigin : '') || '').trim();
  if (onVercel && !configured) {
    throw new Error('Set BACKEND_API_URL to the Render backend HTTPS origin before deploying.');
  }
  const candidate = configured || env.NEXT_PUBLIC_API_URL || env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';
  let url;
  try { url = new URL(String(candidate).trim()); } catch {
    throw new Error('BACKEND_API_URL must be an absolute backend origin.');
  }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password ||
      url.search || url.hash || url.pathname !== '/') {
    throw new Error('BACKEND_API_URL must contain only the backend origin, without credentials, a path, query, or fragment.');
  }
  if (onVercel && (url.protocol !== 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) || url.hostname.endsWith('.localhost'))) {
    throw new Error('Vercel requires a public HTTPS BACKEND_API_URL; localhost is for local development.');
  }
  return url.origin;
}

module.exports = { resolveBackendOrigin };
