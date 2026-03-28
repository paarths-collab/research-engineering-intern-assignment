from __future__ import annotations

from perspective.models.schemas import PersonaOutput, PerspectiveGraphEdge, PerspectiveGraphNode


def build_graph(topic: str, headline: str, description: str, persona_outputs: list[PersonaOutput]) -> tuple[list[PerspectiveGraphNode], list[PerspectiveGraphEdge]]:
    nodes: list[PerspectiveGraphNode] = []
    edges: list[PerspectiveGraphEdge] = []

    situation_id = "news-0"
    nodes.append(
        PerspectiveGraphNode(
            id=situation_id,
            type="newsNode",
            position={"x": 120, "y": 200},
            data={
                "label": "News",
                "topic": topic,
                "headline": headline,
                "description": description,
            },
        )
    )

    x_start = 560
    x_gap = 360

    for idx, output in enumerate(persona_outputs):
        x = x_start + (idx * x_gap)
        persona_id = f"persona-{idx}"

        nodes.append(
            PerspectiveGraphNode(
                id=persona_id,
                type="personaNode",
                position={"x": x, "y": 140},
                data={
                    "label": output.persona_name,
                    "persona": output.persona_name,
                    "interpretation": output.interpretation,
                    "reaction": output.reaction,
                },
            )
        )

        edges.append(PerspectiveGraphEdge(id=f"e-{situation_id}-{persona_id}", source=situation_id, target=persona_id, animated=True))

    return nodes, edges
