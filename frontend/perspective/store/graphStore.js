import { create } from 'zustand';
import { applyNodeChanges, applyEdgeChanges, addEdge } from 'reactflow';

const ensureUniqueNodeId = (desiredId, existingNodes) => {
  const used = new Set(existingNodes.map((n) => n.id));
  if (!used.has(desiredId)) return desiredId;

  let suffix = 1;
  let candidate = `${desiredId}-${suffix}`;
  while (used.has(candidate)) {
    suffix += 1;
    candidate = `${desiredId}-${suffix}`;
  }
  return candidate;
};

const dedupeNodesById = (nodes) => {
  const out = [];
  const seen = new Set();
  nodes.forEach((node) => {
    if (!node || !node.id || seen.has(node.id)) return;
    seen.add(node.id);
    out.push(node);
  });
  return out;
};

const dedupeEdges = (edges) => {
  const out = [];
  const seenIds = new Set();
  const seenPairs = new Set();

  edges.forEach((edge) => {
    if (!edge || !edge.source || !edge.target) return;
    const id = String(edge.id || '');
    const pair = `${edge.source}=>${edge.target}`;
    if (id && seenIds.has(id)) return;
    if (seenPairs.has(pair)) return;
    if (id) seenIds.add(id);
    seenPairs.add(pair);
    out.push(edge);
  });

  return out;
};

const makeUniqueEdgeId = (connection, existingEdges) => {
  const used = new Set(existingEdges.map((e) => String(e.id || '')));
  const source = String(connection.source || 'source');
  const target = String(connection.target || 'target');
  const sourceHandle = String(connection.sourceHandle || '');
  const targetHandle = String(connection.targetHandle || '');

  const base = `e-${source}-${sourceHandle}-${target}-${targetHandle}`;
  if (!used.has(base)) return base;

  let suffix = 1;
  let candidate = `${base}-${suffix}`;
  while (used.has(candidate)) {
    suffix += 1;
    candidate = `${base}-${suffix}`;
  }
  return candidate;
};

const useGraphStore = create((set, get) => ({
  nodes: [],
  edges: [],
  isSimulating: false,
  simulationResult: null,
  debateRounds: 3,

  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) }),

  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),

  onConnect: (connection) =>
    set(() => {
      const currentEdges = get().edges;
      const exists = currentEdges.some((e) =>
        e.source === connection.source
        && e.target === connection.target
        && (e.sourceHandle || null) === (connection.sourceHandle || null)
        && (e.targetHandle || null) === (connection.targetHandle || null)
      );

      if (exists) {
        return { edges: currentEdges };
      }

      const id = makeUniqueEdgeId(connection, currentEdges);
      const next = addEdge({ ...connection, id, type: 'smoothstep', animated: true }, currentEdges);
      return { edges: dedupeEdges(next) };
    }),

  addNode: (node) =>
    set(() => {
      const current = get().nodes;
      const safeId = ensureUniqueNodeId(node.id, current);
      const safeNode = safeId === node.id ? node : { ...node, id: safeId };
      return { nodes: [...current, safeNode] };
    }),

  deleteNode: (nodeId) =>
    set({
      nodes: get().nodes.filter((n) => n.id !== nodeId),
      edges: get().edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
    }),

  deleteSelectedNodes: () => {
    const selectedIds = new Set(get().nodes.filter((n) => n.selected).map((n) => n.id));
    if (selectedIds.size === 0) return;

    set({
      nodes: get().nodes.filter((n) => !selectedIds.has(n.id)),
      edges: get().edges.filter((e) => !selectedIds.has(e.source) && !selectedIds.has(e.target)),
    });
  },

  focusNode: (nodeId) =>
    set({
      nodes: get().nodes.map((n) => ({ ...n, selected: n.id === nodeId })),
    }),

  resetGraph: () =>
    set({ nodes: [], edges: [], simulationResult: null }),

  setSimulating: (v) => set({ isSimulating: v }),

  setDebateRounds: (v) => {
    const parsed = Number(v);
    const safe = Number.isFinite(parsed) ? Math.max(1, Math.min(20, Math.round(parsed))) : 3;
    set({ debateRounds: safe });
  },

  applySimulationResult: (result) => {
    const rawNodes = Array.isArray(result.nodes) ? result.nodes : [];
    const rawEdges = Array.isArray(result.edges) ? result.edges : [];
    // Replace a requested connector only when exactly one output belongs to it.
    // Shared connectors and mixed boards keep every per-headline result.
    const outputsByConnector = new Map();
    rawNodes.forEach((node) => {
      if (!node.data?.generated_output) return;
      (node.data?.connectorIds || []).forEach((id) => {
        const outputs = outputsByConnector.get(id) || [];
        outputs.push(node);
        outputsByConnector.set(id, outputs);
      });
    });
    const replacements = new Map();
    const mergedNodes = new Map();
    rawNodes.forEach((node) => {
      const outputs = outputsByConnector.get(node.id) || [];
      const output = outputs[0];
      if (outputs.length !== 1 || output?.type !== node.type || output.data?.connectorIds?.length !== 1) return;
      replacements.set(output.id, node.id);
      mergedNodes.set(node.id, {
        ...node,
        data: { ...node.data, ...output.data, generated_output: false },
      });
    });
    const uniqueKeptNodes = dedupeNodesById(rawNodes
      .filter((node) => !replacements.has(node.id))
      .map((node) => mergedNodes.get(node.id) || node));

    const keptIds = new Set(uniqueKeptNodes.map((n) => n.id));
    const keptEdges = dedupeEdges(rawEdges.map((edge) => ({
      ...edge,
      source: replacements.get(edge.source) || edge.source,
      target: replacements.get(edge.target) || edge.target,
    })).filter((edge) => keptIds.has(edge.source) && keptIds.has(edge.target) && edge.source !== edge.target));

    set({ nodes: uniqueKeptNodes, edges: keptEdges, simulationResult: result, isSimulating: false });
  }
}));

export default useGraphStore;
