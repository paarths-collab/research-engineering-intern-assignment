from __future__ import annotations
from datetime import date
from pydantic import BaseModel

class MediaBriefRequest(BaseModel):
    subreddit: str

class SpikeRequest(BaseModel):
    spike_date: date
    force_enrichment: bool = False
