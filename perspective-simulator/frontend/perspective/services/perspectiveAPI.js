const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function simulateGraph(nodes, edges) {
  const response = await fetch(`${API_BASE}/api/perspective/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ nodes, edges })
  });
  if (!response.ok) throw new Error(`Simulation failed: ${await response.text()}`);
  return response.json();
}
