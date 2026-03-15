import os
import json
import math
import uuid
import httpx
from typing import List, Dict, Any, Tuple

from ..models.graph_models import GraphNode, GraphEdge
from ..prompts.persona_prompts import SIMULATE_SYSTEM_PROMPT, build_simulation_prompt

CONFLICT_THRESHOLD = 0.45


def compute_ideology_distance(persona_a: GraphNode, persona_b: GraphNode) -> float:
    """Compute cosine distance between ideology vectors."""
    vec_a = persona_a.data.ideology_vector
    vec_b = persona_b.data.ideology_vector

    if not vec_a or not vec_b:
        # Fallback: trait overlap heuristic
        traits_a = set(persona_a.data.traits or [])
        traits_b = set(persona_b.data.traits or [])
        if not traits_a or not traits_b:
            return 0.5
        overlap = len(traits_a & traits_b)
        union = len(traits_a | traits_b)
        return 1.0 - (overlap / union) if union > 0 else 0.5

    if len(vec_a) != len(vec_b):
        return 0.5

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a ** 2 for a in vec_a))
    mag_b = math.sqrt(sum(b ** 2 for b in vec_b))

    if mag_a == 0 or mag_b == 0:
        return 0.5

    similarity = dot / (mag_a * mag_b)
    return (1.0 - similarity) / 2.0  # Normalize to [0, 1]


async def call_claude_api(personas: list, news_node: GraphNode) -> Dict[str, Any]:
    """Call Claude API for nuanced simulation."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return None

    prompt = build_simulation_prompt(
        personas,
        news_node.data.label,
        news_node.data.description or ""
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-5-haiku-20241022",
                    "max_tokens": 512,
                    "system": SIMULATE_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
            if response.status_code == 200:
                data = response.json()
                text = data["content"][0]["text"]
                return json.loads(text)
    except Exception:
        pass
    return None


def build_result_nodes_edges(
    existing_nodes: List[Dict],
    existing_edges: List[Dict],
    news_node: GraphNode,
    result_type: str,
    connected_personas: List[GraphNode],
    summary: str,
    ideology_distance: float
) -> Tuple[List[Dict], List[Dict]]:
    """Build the new result node and edges."""
    # Find news node position
    news_pos = news_node.position or {"x": 400, "y": 300}
    result_x = news_pos["x"]
    result_y = news_pos["y"] + 200

    result_id = f"{result_type}-{uuid.uuid4().hex[:8]}"

    result_node = {
        "id": result_id,
        "type": result_type,
        "position": {"x": result_x - 75, "y": result_y},
        "data": {
            "label": "Discussion" if result_type == "discussion" else "Debate",
            "type": result_type,
            "description": summary,
            "ideology_distance": round(ideology_distance, 2),
            "persona_count": len(connected_personas)
        }
    }

    result_edge = {
        "id": f"edge-news-{result_id}",
        "source": news_node.id,
        "target": result_id,
        "type": "smoothstep",
        "animated": True,
        "style": {"stroke": "#22c55e" if result_type == "discussion" else "#ef4444"}
    }

    return [result_node], [result_edge]


async def simulate_graph(
    nodes: List[GraphNode],
    edges: List[GraphEdge]
) -> Dict[str, Any]:
    """Main simulation algorithm."""
    node_map = {n.id: n for n in nodes}

    # Identify news nodes
    news_nodes = [n for n in nodes if n.type == "news"]

    new_nodes = []
    new_edges = []
    overall_result_type = None
    overall_summary = None

    for news_node in news_nodes:
        # Find all personas connected to this news node
        persona_ids = []
        for edge in edges:
            if edge.target == news_node.id and edge.source in node_map:
                src = node_map[edge.source]
                if src.type == "persona":
                    persona_ids.append(src.id)
            # Also handle persona->news direction
            if edge.source == news_node.id and edge.target in node_map:
                tgt = node_map[edge.target]
                if tgt.type == "persona":
                    persona_ids.append(tgt.id)

        # Deduplicate
        persona_ids = list(dict.fromkeys(persona_ids))
        connected_personas = [node_map[pid] for pid in persona_ids if pid in node_map]

        if len(connected_personas) < 2:
            continue  # Need at least 2 personas

        # Compute ideology distance (pairwise max)
        max_distance = 0.0
        for i in range(len(connected_personas)):
            for j in range(i + 1, len(connected_personas)):
                d = compute_ideology_distance(connected_personas[i], connected_personas[j])
                max_distance = max(max_distance, d)

        # Optionally call Claude for richer analysis
        persona_dicts = [
            {"label": p.data.label, "traits": p.data.traits or []}
            for p in connected_personas
        ]
        claude_result = await call_claude_api(persona_dicts, news_node)

        if claude_result:
            result_type = claude_result.get("result_type", "discussion")
            summary = claude_result.get("summary", "Perspectives analyzed.")
            ideology_distance = claude_result.get("ideology_distance", max_distance)
        else:
            result_type = "debate" if max_distance >= CONFLICT_THRESHOLD else "discussion"
            summary = (
                f"Strong ideological conflict detected between {len(connected_personas)} perspectives."
                if result_type == "debate"
                else f"{len(connected_personas)} perspectives find common ground on this topic."
            )
            ideology_distance = max_distance

        overall_result_type = result_type
        overall_summary = summary

        rn, re = build_result_nodes_edges(
            [n.__dict__ for n in nodes],
            [e.__dict__ for e in edges],
            news_node, result_type,
            connected_personas, summary, ideology_distance
        )
        new_nodes.extend(rn)
        new_edges.extend(re)

    # Serialize existing nodes/edges
    all_nodes = [
        {
            "id": n.id,
            "type": n.type,
            "position": n.position or {"x": 0, "y": 0},
            "data": n.data.dict()
        }
        for n in nodes
    ]
    all_edges = [
        {
            "id": e.id,
            "source": e.source,
            "target": e.target,
            "type": e.type or "smoothstep",
            "animated": True
        }
        for e in edges
    ]

    return {
        "nodes": all_nodes + new_nodes,
        "edges": all_edges + new_edges,
        "result_type": overall_result_type,
        "summary": overall_summary
    }
