import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { apiFetch, setOperatorToken, hasOperatorToken, subscribeOperatorAccess } from '../lib/operatorAccess.mjs';
import { graphRequest } from '../lib/graphRequest.mjs';
import { subscribeAuthRequired } from '../lib/authClient.mjs';

const originalFetch = globalThis.fetch;
const originalLocation = globalThis.location;
const originalBackendUrl = process.env.NEXT_PUBLIC_API_BASE_URL;
const token = 'test-token-' + 'x'.repeat(32);
afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.location = originalLocation;
  setOperatorToken('');
  if (originalBackendUrl === undefined) delete process.env.NEXT_PUBLIC_API_BASE_URL;
  else process.env.NEXT_PUBLIC_API_BASE_URL = originalBackendUrl;
});

test('user analysis uses same-origin cookie and CSRF while manual admin uses only its bearer', async () => {
  globalThis.location = { origin: 'http://localhost:3000' };
  let calls = [];
  globalThis.fetch = async (...args) => { calls.push(args); return new Response('{}'); };
  await apiFetch('/api/perspective/simulate', { method: 'POST', credentials: 'include', headers: { Authorization: 'Bearer unwanted' } });
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.equal(calls[0][1].headers.get('X-Narrative-CSRF'), '1');
  assert.equal(calls[0][1].headers.get('Authorization'), null);
  assert.equal(calls[0][1].redirect, 'error');
  let updates = 0;
  const unsubscribe = subscribeOperatorAccess(() => updates++);
  setOperatorToken(token);
  await apiFetch('/api/globe/pipeline/run', { method: 'POST' });
  assert.equal(calls[1][1].headers.get('Authorization'), `Bearer ${token}`);
  assert.equal(calls[1][1].credentials, 'omit');
  assert.equal(calls[1][1].redirect, 'error');
  await apiFetch('/api/globe/events/map');
  assert.equal(calls[2][1].headers, undefined);
  setOperatorToken('');
  assert.equal(hasOperatorToken(), false);
  assert.equal(updates, 2);
  unsubscribe();
});

test('session and operator credentials never leave for an unconfigured origin or non-API URL', async () => {
  globalThis.location = { origin: 'https://narrative.example' };
  globalThis.fetch = () => { throw new Error('must not reach fetch'); };
  for (const credential of ['', token]) {
    setOperatorToken(credential);
    for (const url of ['https://other.example/api/action', '//other.example/api/action', '/uploads/action', 'https://secret@narrative.example/api/action']) {
      await assert.rejects(apiFetch(url, { method: 'POST' }), /same-origin API/);
    }
  }
});

test('configured absolute backend analysis is proxied through the frontend session origin', async () => {
  globalThis.location = { origin: 'https://narrative.example' };
  process.env.NEXT_PUBLIC_API_BASE_URL = 'https://backend.example';
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/chatbot/query?scope=one');
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.headers.get('X-Narrative-CSRF'), '1');
    assert.equal(init.headers.has('Authorization'), false);
    return Response.json({});
  };
  await apiFetch('https://backend.example/api/chatbot/query?scope=one', { method: 'POST' });
});

test('expired user sessions notify account UI with an actionable sign-in error', async () => {
  globalThis.location = { origin: 'https://narrative.example' };
  let notices = 0;
  const unsubscribe = subscribeAuthRequired(() => notices++);
  globalThis.fetch = async () => Response.json({ detail: 'Private backend internals' }, { status: 401 });
  try {
    await assert.rejects(apiFetch('/api/chatbot/query', { method: 'POST' }), /Sign in to run analysis/);
    assert.equal(notices, 1);
  } finally { unsubscribe(); }
});

test('operator wrapper cannot send a bearer to account endpoints', async () => {
  globalThis.location = { origin: 'https://narrative.example' };
  setOperatorToken(token);
  globalThis.fetch = () => { throw new Error('must not reach fetch'); };
  await assert.rejects(apiFetch('/api/auth/register', { method: 'POST' }), /account client/);
});

test('auth and work errors are actionable; bad token clears from memory', async () => {
  globalThis.location = { origin: 'https://narrative.example' };
  setOperatorToken(token);
  globalThis.fetch = async () => Response.json({ detail: 'Work budget exceeded' }, { status: 429 });
  await assert.rejects(apiFetch('/api/perspective/simulate', { method: 'POST' }), /Work budget exceeded/);
  assert.equal(hasOperatorToken(), true);
  globalThis.fetch = async () => Response.json({ detail: 'A valid operator bearer token is required' }, { status: 401 });
  await assert.rejects(apiFetch('/api/perspective/simulate', { method: 'POST' }), /valid operator/);
  assert.equal(hasOperatorToken(), false);
});

test('repeated simulation sends original context and drops derived work', () => {
  const nodes = [
    { id: 'p', type: 'persona', position: {}, data: { label: 'Persona', reactions: ['derived'] } },
    { id: 'n', type: 'news', position: {}, data: { label: 'Story', description: 'enriched', input_description: 'original',
      input_reports: [], globe_reports: ['enriched'], rounds: ['x'.repeat(300000)], is_mock: true, data_source: 'mock_sample' } },
    { id: 'd', type: 'debate', position: {}, data: { label: 'Original connector', generated_output: false } },
    { id: 'result', type: 'debate', position: {}, data: { generated_output: true } },
    { id: 'a', type: 'analysis', position: {}, data: {} },
  ];
  const edges = [{ id: 'e', source: 'p', target: 'n', targetHandle: 'input' }, { id: 'g', source: 'n', target: 'result' }];
  const request = graphRequest(nodes, edges, { debateRounds: 3 });
  assert.deepEqual(request.nodes.map(n => n.id), ['p', 'n', 'd']);
  assert.equal(request.nodes[1].data.description, 'original');
  assert.deepEqual(request.nodes[1].data.globe_reports, []);
  assert.equal(request.nodes[1].data.is_mock, true);
  assert.equal(request.nodes[1].data.rounds, undefined);
  assert.equal(request.edges.length, 1);
  assert.equal(request.edges[0].targetHandle, 'input');
  assert.equal(request.debate_rounds, 3);
  assert.ok(JSON.stringify(request).length < 2000);
});
