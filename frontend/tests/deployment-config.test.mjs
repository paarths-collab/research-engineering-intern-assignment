import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { resolveBackendOrigin } = require('../lib/deploymentConfig.cjs');
const config = require('../next.config.js');
const rootVercel = require('../../vercel.json');
const frontendVercel = require('../vercel.json');

test('local development keeps a backend default and explicit backend takes priority', () => {
  assert.equal(resolveBackendOrigin({}), 'http://127.0.0.1:8000');
  assert.equal(resolveBackendOrigin({ BACKEND_API_URL: 'https://backend.example/', NEXT_PUBLIC_API_URL: 'https://stale.example' }), 'https://backend.example');
});

test('Vercel cannot deploy an API proxy with an absent or local backend', () => {
  for (const backend of ['', 'http://backend.example', 'https://localhost', 'https://127.0.0.1', 'https://[::1]']) {
    assert.throws(() => resolveBackendOrigin({ VERCEL: '1', BACKEND_API_URL: backend }));
  }
  assert.equal(resolveBackendOrigin({ VERCEL: '1', BACKEND_API_URL: 'https://backend.example/' }), 'https://backend.example');
});

test('backend configuration excludes credentials and accidental API paths', () => {
  for (const value of ['not-a-url', 'https://user:token@backend.example', 'https://backend.example/api', 'https://backend.example?token=test', 'https://backend.example#fragment']) {
    assert.throws(() => resolveBackendOrigin({ BACKEND_API_URL: value }));
  }
});

test('root and frontend Vercel configurations only build the frontend', async () => {
  assert.deepEqual(rootVercel.builds, [{ src: 'frontend/package.json', use: '@vercel/next' }]);
  assert.equal(rootVercel.rewrites, undefined);
  assert.equal(frontendVercel.installCommand, 'npm ci');
  assert.equal(frontendVercel.framework, 'nextjs');
  const [rewrite] = await config.rewrites();
  assert.equal(rewrite.source, '/api/:path*');
  assert.ok(rewrite.destination.endsWith('/api/:path*'));
  assert.ok(!rewrite.destination.includes('index.py'));
});

test('the verified production deployment origin is a Vercel fallback, without changing local defaults', () => {
  const { backendOrigin } = require('../deployment.json');
  assert.equal(resolveBackendOrigin({ VERCEL: '1' }, backendOrigin), backendOrigin);
  assert.equal(resolveBackendOrigin({}, backendOrigin), 'http://127.0.0.1:8000');
  assert.equal(resolveBackendOrigin({ VERCEL: '1', BACKEND_API_URL: 'https://override.example' }, backendOrigin), 'https://override.example');
});
