import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { getAuthStatus, getCurrentUser, safeNextPath, signIn, signOut, signUp } from '../lib/authClient.mjs';
import { setOperatorToken } from '../lib/operatorAccess.mjs';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; setOperatorToken(''); });

test('login submits form fields with CSRF and a same-origin session, never operator elevation', async () => {
  setOperatorToken('private-operator-test-token-' + 'x'.repeat(32));
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/auth/login');
    assert.equal(init.method, 'POST');
    assert.equal(init.body.get('username'), 'person@example.test');
    assert.equal(init.body.get('password'), 'a valid test password');
    assert.deepEqual([...init.body.keys()], ['username', 'password']);
    assert.equal(init.headers.get('Content-Type'), 'application/x-www-form-urlencoded');
    assert.equal(init.headers.get('X-Narrative-CSRF'), '1');
    assert.equal(init.headers.has('Authorization'), false);
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.redirect, 'error');
    assert.equal(init.cache, 'no-store');
    return new Response(null, { status: 204 });
  };
  await signIn(' person@example.test ', 'a valid test password');
});

test('signup sends only account fields and signs in after successful registration', async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return url.endsWith('/register') ? Response.json({ id: 'new-user', email: 'person@example.test' }, { status: 201 }) : new Response(null, { status: 204 });
  };
  await signUp(' person@example.test ', 'a valid test password');
  assert.deepEqual(calls.map(({ url }) => url), ['/api/auth/register', '/api/auth/login']);
  assert.deepEqual(JSON.parse(calls[0].init.body), { email: 'person@example.test', password: 'a valid test password' });
  for (const { init } of calls) {
    assert.equal(init.headers.get('X-Narrative-CSRF'), '1');
    assert.equal(init.headers.has('Authorization'), false);
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.redirect, 'error');
  }
});

test('failed signup does not attempt login or expose whether an account exists', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls++; return Response.json({ detail: 'REGISTER_USER_ALREADY_EXISTS' }, { status: 400 }); };
  await assert.rejects(signUp('person@example.test', 'a valid test password'), (error) => {
    assert.equal(error.status, 400);
    assert.match(error.message, /Unable to create this account/);
    assert.doesNotMatch(error.message, /ALREADY_EXISTS/);
    return true;
  });
  assert.equal(calls, 1);
});

test('logout is a CSRF-protected cookie request without an operator credential', async () => {
  setOperatorToken('private-operator-test-token-' + 'x'.repeat(32));
  globalThis.fetch = async (url, init) => {
    assert.equal(url, '/api/auth/logout');
    assert.equal(init.method, 'POST');
    assert.equal(init.headers.get('X-Narrative-CSRF'), '1');
    assert.equal(init.headers.has('Authorization'), false);
    assert.equal(init.credentials, 'same-origin');
    return new Response(null, { status: 204 });
  };
  await signOut();
});

test('session lookup treats 401 as signed out and keeps configuration requests credential scoped', async () => {
  globalThis.fetch = async (url, init) => {
    assert.equal(init.credentials, 'same-origin');
    assert.equal(init.headers.has('Authorization'), false);
    assert.equal(init.headers.has('X-Narrative-CSRF'), false);
    return url.endsWith('/me') ? new Response(null, { status: 401 }) : Response.json({ configured: true });
  };
  assert.equal(await getCurrentUser(), null);
  assert.deepEqual(await getAuthStatus(), { configured: true });
});

test('account failures use generic login feedback and actionable throttling feedback', async () => {
  globalThis.fetch = async () => Response.json({ detail: 'LOGIN_BAD_CREDENTIALS' }, { status: 400 });
  await assert.rejects(signIn('person@example.test', 'wrong password'), /Unable to sign in. Check your email and password/);
  globalThis.fetch = async () => new Response(null, { status: 429 });
  await assert.rejects(signIn('person@example.test', 'wrong password'), /Too many attempts/);
});

test('account return paths stay internal and avoid admin and account redirect loops', () => {
  assert.equal(safeNextPath('/perspective?story=one#canvas'), '/perspective?story=one#canvas');
  for (const path of ['https://other.example', '//other.example', '/\\other.example', '/%2f%2fother.example', '/%5Cother.example', '/overview%0a', '/login?next=/globe', '/signup', '/admin', '/admin/collection', '/%61dmin', ['//other.example'], null]) {
    assert.equal(safeNextPath(path), '/overview', String(path));
  }
});
