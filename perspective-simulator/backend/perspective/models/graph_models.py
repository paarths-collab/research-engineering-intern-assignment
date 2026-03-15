from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class NodeData(BaseModel):
    label: str
    type: str
    description: Optional[str] = None
    traits: Optional[List[str]] = None
    ideology_vector: Optional[List[float]] = None


class GraphNode(BaseModel):
    id: str
    type: str
    data: NodeData
    position: Optional[Dict[str, float]] = None


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    type: Optional[str] = None


class SimulateRequest(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class SimulateResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    result_type: Optional[str] = None
    summary: Optional[str] = None
