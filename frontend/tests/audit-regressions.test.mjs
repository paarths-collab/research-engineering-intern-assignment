import assert from 'node:assert/strict';
import { test } from 'node:test';
import store from '../perspective/store/graphStore.js';
import { dataProvenance, sourceLabel } from '../lib/dataProvenance.mjs';
import { normalizePins } from '../lib/globeData.mjs';
import { loadNewsPresets } from '../perspective/services/perspectiveAPI.js';

const node = (id, type, data = {}) => ({ id, type, position: { x: 0, y: 0 }, data });
const edge = (id, source, target, handles = {}) => ({ id, source, target, ...handles });

test('shared and mixed boards retain every generated branch', () => {
  const nodes = [node('p', 'persona'), node('d', 'debate'), node('n1', 'news'), node('n2', 'news'),
    node('n3', 'news'), node('a3', 'analysis'),
    node('d1', 'debate', { connectorIds: ['d'], generated_output: true }),
    node('d2', 'debate', { connectorIds: ['d'], generated_output: true })];
  const edges = [edge('e1', 'p', 'd'), edge('e2', 'd', 'n1'), edge('e3', 'd', 'n2'),
    edge('e4', 'd1', 'n1'), edge('e5', 'd2', 'n2'), edge('e6', 'n3', 'a3')];
  store.getState().applySimulationResult({ nodes, edges, result_type: 'debate' });
  assert.deepEqual(store.getState().nodes.map(n => n.id), nodes.map(n => n.id));
  assert.equal(store.getState().edges.length, edges.length);
});

test('one output updates the original connector without losing handle attachments', () => {
  const nodes = [node('p', 'persona'), node('d', 'debate'), node('n', 'news'),
    node('result', 'debate', { connectorIds: ['d'], generated_output: true, simulated: true })];
  const edges = [edge('input', 'p', 'd', { sourceHandle: 'out', targetHandle: 'in-left' }),
    edge('news', 'd', 'n', { sourceHandle: 'out-bottom', targetHandle: 'in' }),
    edge('generated1', 'p', 'result'), edge('generated2', 'result', 'n')];
  store.getState().applySimulationResult({ nodes, edges, result_type: 'debate' });
  assert.deepEqual(store.getState().nodes.map(n => n.id), ['p', 'd', 'n']);
  assert.equal(store.getState().nodes[1].data.generated_output, false);
  assert.equal(store.getState().nodes[1].data.simulated, true);
  assert.equal(store.getState().edges.length, 2);
  assert.equal(store.getState().edges[0].targetHandle, 'in-left');
});

test('map normalizes sample provenance and its visible label', () => {
  const [pin] = normalizePins({ is_mock: true, data_source: 'mock_sample', data_notice: 'Demo only',
    pins: [{ id: 'mock-1', lat: 1, lon: 2, title: 'Sample headline' }] });
  assert.equal(pin.is_mock, true);
  assert.equal(pin.data_notice, 'Demo only');
  assert.equal(sourceLabel(pin), 'Demo sample');
  assert.equal(sourceLabel({ data_source: 'pipeline_output' }), 'Pipeline snapshot');
  assert.equal(sourceLabel(dataProvenance({})), 'Source unverified');
});

test('preset cache round trip keeps sample labels and supporting reports', async () => {
  const savedFetch = globalThis.fetch;
  const savedWindow = globalThis.window;
  const storage = new Map();
  globalThis.window = { localStorage: {
    getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value),
  } };
  const report = { title: 'Sample report', link: 'https://example.test/a' };
  globalThis.fetch = async () => ({ ok: true, text: async () => JSON.stringify({ news: [{
    label: 'Sample', event_id: 'mock-1', is_mock: true, data_source: 'mock_sample',
    data_notice: 'Demo only', reports: [report],
  }] }) });
  try {
    const response = await loadNewsPresets();
    assert.equal(response.source, 'backend');
    assert.equal(sourceLabel(response.items[0]), 'Demo sample');
    globalThis.fetch = async () => { throw new Error('offline'); };
    const cached = await loadNewsPresets();
    assert.equal(cached.source, 'cache');
    assert.deepEqual(cached.items, response.items);
    assert.deepEqual(cached.items[0].globe_reports, [report]);
  } finally {
    globalThis.fetch = savedFetch;
    if (savedWindow === undefined) delete globalThis.window;
    else globalThis.window = savedWindow;
  }
});
