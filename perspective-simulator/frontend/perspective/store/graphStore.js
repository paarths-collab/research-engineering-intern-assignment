import { create } from 'zustand';
import { applyNodeChanges, applyEdgeChanges, addEdge } from 'reactflow';

const useGraphStore = create((set, get) => ({
  nodes: [],
  edges: [],
  isSimulating: false,
  simulationResult: null,

  onNodesChange: (changes) =>
    set({ nodes: applyNodeChanges(changes, get().nodes) }),

  onEdgesChange: (changes) =>
    set({ edges: applyEdgeChanges(changes, get().edges) }),

  onConnect: (connection) =>
    set({ edges: addEdge({ ...connection, type: 'smoothstep', animated: true }, get().edges) }),

  addNode: (node) =>
    set({ nodes: [...get().nodes, node] }),

  resetGraph: () =>
    set({ nodes: [], edges: [], simulationResult: null }),

  setSimulating: (v) => set({ isSimulating: v }),

  applySimulationResult: (result) => {
    set({ nodes: result.nodes, edges: result.edges, simulationResult: result, isSimulating: false });
  }
}));

export default useGraphStore;
