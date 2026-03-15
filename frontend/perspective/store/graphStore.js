import { create } from 'zustand';
import { applyNodeChanges, applyEdgeChanges, addEdge } from 'reactflow';

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
    set({ edges: addEdge({ ...connection, type: 'smoothstep', animated: true }, get().edges) }),

  addNode: (node) =>
    set({ nodes: [...get().nodes, node] }),

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

    const lastDiscussion = [...rawNodes].reverse().find((n) => n.type === 'discussion');
    const lastDebate = [...rawNodes].reverse().find((n) => n.type === 'debate');

    const keptNodes = rawNodes.filter((n) => n.type !== 'discussion' && n.type !== 'debate');
    if (lastDiscussion) keptNodes.push(lastDiscussion);
    if (lastDebate) keptNodes.push(lastDebate);

    const keptIds = new Set(keptNodes.map((n) => n.id));
    const keptEdges = rawEdges.filter((e) => keptIds.has(e.source) && keptIds.has(e.target));

    set({ nodes: keptNodes, edges: keptEdges, simulationResult: result, isSimulating: false });
  }
}));

export default useGraphStore;
