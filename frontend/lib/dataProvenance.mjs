export function dataProvenance(payload = {}) {
  const isMock = payload.is_mock === true || payload.data_source === 'mock_sample'
    || /^mock-/.test(String(payload.event_id || payload.id || ''));
  return {
    is_mock: isMock,
    data_source: isMock ? 'mock_sample' : payload.data_source || 'unknown',
    data_generated_at: payload.data_generated_at || null,
    data_notice: payload.data_notice || (isMock ? 'Built-in demo events, not real reporting.' : null),
  };
}

export function sourceLabel(payload) {
  const source = dataProvenance(payload);
  if (source.is_mock) return 'Demo sample';
  return {
    pipeline_output: 'Pipeline snapshot',
    external_search: 'External search',
    cached_analysis: 'Cached analysis',
  }[source.data_source] || 'Source unverified';
}
