from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class PerspectiveSimulateRequest(BaseModel):
    nodes: list[PerspectiveGraphNode] = Field(default_factory=list)
    edges: list[PerspectiveGraphEdge] = Field(default_factory=list)
    debate_rounds: int = Field(default=3, ge=1, le=20)
    options: dict[str, Any] = Field(default_factory=dict)


class PerspectiveSimulateResponse(BaseModel):
    nodes: list[PerspectiveGraphNode]
    edges: list[PerspectiveGraphEdge]
    generated: list[dict[str, str]] = Field(default_factory=list)
    result_type: str = "analysis"
    summary: str = ""


class PerspectiveError(BaseModel):
    error: str
