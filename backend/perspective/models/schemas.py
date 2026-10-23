from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer, model_validator


class PersonaConfig(BaseModel):
    name: str
    type: str
    traits: list[str] = Field(default_factory=list)
    style: str = ""
    bias: str = ""
    prompt_key: str = "default"


PerspectiveNodeType = Literal["persona", "news", "discussion", "debate", "analysis"]


class PerspectiveGraphNode(BaseModel):
    id: str
    type: PerspectiveNodeType
    position: dict[str, float]
    data: dict[str, Any] = Field(default_factory=dict)


class PerspectiveGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: str = "smoothstep"
    animated: bool = True
    style: dict[str, Any] | None = None
    # Optional React Flow handle ids; passed through from the request so the
    # frontend can re-attach edges to the same handles after a simulate round trip.
    sourceHandle: str | None = None
    targetHandle: str | None = None

    @model_serializer(mode="wrap")
    def _omit_empty_handles(self, handler):
        data = handler(self)
        for key in ("sourceHandle", "targetHandle"):
            if data.get(key) is None:
                data.pop(key, None)
        return data


class PerspectiveSimulateRequest(BaseModel):
    nodes: list[PerspectiveGraphNode] = Field(default_factory=list, max_length=64)
    edges: list[PerspectiveGraphEdge] = Field(default_factory=list, max_length=128)
    debate_rounds: int = Field(default=3, ge=1, le=20)
    options: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_inputs(self):
        from api_security import _bounded_json
        if len({n.id for n in self.nodes}) != len(self.nodes):
            raise ValueError("Node ids must be unique")
        if len({e.id for e in self.edges}) != len(self.edges):
            raise ValueError("Edge ids must be unique")
        for node in self.nodes:
            if len(node.id) > 64 or not _bounded_json(node.data):
                raise ValueError("Node id or data exceeds input limits")
        for edge in self.edges:
            if len(edge.id) > 128 or max(len(edge.source), len(edge.target)) > 64:
                raise ValueError("Edge identifiers exceed input limits")
        return self


class PerspectiveSimulateResponse(BaseModel):
    nodes: list[PerspectiveGraphNode]
    edges: list[PerspectiveGraphEdge]
    generated: list[dict[str, str]] = Field(default_factory=list)
    result_type: str = "analysis"
    summary: str = ""
    simulated: bool = True
    simulation_notice: str = ""
    generation: dict[str, Any] = Field(default_factory=dict)


class PerspectiveError(BaseModel):
    error: str
