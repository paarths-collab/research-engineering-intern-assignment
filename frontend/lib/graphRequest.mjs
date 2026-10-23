// Send original board inputs; generated text is output, not fresh prompt context.
const inputFields = ['label', 'name', 'description', 'persona_prompt', 'traits', 'ideology_vector',
  'event_id', 'risk_level', 'impact_score', 'strategic_implications', 'globe_reports',
  'is_mock', 'data_source', 'data_generated_at', 'data_notice'];
export function graphRequest(nodes, edges, options = {}) {
  const inputs = nodes.filter((node) => node.type !== 'analysis' && !node.data?.generated_output)
    .map(({ id, type, position, data = {} }) => {
      const clean = Object.fromEntries(inputFields.filter((key) => key in data).map((key) => [key, data[key]]));
      if ('input_description' in data) clean.description = data.input_description;
      if ('input_reports' in data) clean.globe_reports = data.input_reports;
      return { id, type, position, data: clean };
    });
  const ids = new Set(inputs.map((node) => node.id));
  return {
    nodes: inputs,
    edges: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target))
      .map(({ id, source, target, type, animated, style, sourceHandle, targetHandle }) =>
        ({ id, source, target, type, animated, style, sourceHandle, targetHandle })),
    debate_rounds: options.debateRounds,
    options: {},
  };
}
