from __future__ import annotations
from fastapi import APIRouter, BackgroundTasks, HTTPException
from streamgraph2.data import db
from streamgraph2.logic.pipeline import run_spike_pipeline
from streamgraph2.models.schemas import SpikeRequest

router = APIRouter(tags=["Spike Attribution"])

@router.get("/volume")
async def get_volume():
    """Daily volume series with z-scores. Used for streamgraph / spike detection UI."""
    rows = await db.get_volume_series()
    return {
        "volume": [
            {
                "date"        : str(r["date"]),
                "post_count"  : r["post_count"],
                "rolling_mean": r["rolling_mean"],
                "rolling_std" : r["rolling_std"],
                "z_score"     : r["z_score"],
            }
            for r in rows
        ]
    }

@router.get("/streamgraph")
async def get_streamgraph():
    """Daily volume broken down by subreddit for a true layered Streamgraph."""
    rows = await db.get_streamgraph_series()
    
    # Format for Nivo/D3 Streamgraph: { date: "YYYY-MM-DD", politics: 10, news: 5 }
    data_by_date = {}
    subreddits = set()
    
    for r in rows:
        d_str = str(r["date"])
        sub = r["subreddit"]
        count = r["count"]
        
        if d_str not in data_by_date:
            data_by_date[d_str] = {"date": d_str}
            
        data_by_date[d_str][sub] = count
        subreddits.add(sub)
        
    # Fill missing values with 0 so the d3 stack lays out properly
    result = list(data_by_date.values())
    for item in result:
        for sub in subreddits:
            if sub not in item:
                item[sub] = 0
                
    # Sort chronologically
    result.sort(key=lambda x: x["date"])
    
    return {
        "keys": list(subreddits),
        "data": result
    }

@router.post("/spike-analysis/{narrative_id}")
async def analyze_spike(narrative_id: str, req: SpikeRequest, background_tasks: BackgroundTasks):
    """
    Launch full async spike analysis pipeline:
    Reddit enrichment → BERTopic → News fetch → Cosine match →
    Volume acceleration → Sentiment evolution → Agent supervision → LLM brief

    Returns job_id immediately. Poll /job-status/{job_id}.
    """
    job_id = await db.create_spike_job(req.spike_date)
    background_tasks.add_task(run_spike_pipeline, job_id, req.spike_date)
    return {
        "job_id"    : job_id,
        "narrative_id": narrative_id,
        "spike_date": str(req.spike_date),
        "status"    : "processing",
        "poll_url"  : f"/api/job-status/{job_id}",
    }

@router.get("/job-status/{job_id}")
async def job_status(job_id: str):
    """
    Poll for analysis result.
    Processing → { status: processing }
    Done       → full result: topics, matches, sentiment, brief, metrics, agent_diagnostics
    Failed     → { status: failed, error: ... }
    """
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, f"Job not found: {job_id}")
    if job["status"] == "processing":
        return {"job_id": job_id, "status": "processing"}
    if job["status"] == "failed":
        return {"job_id": job_id, "status": "failed", "error": job["error_msg"]}
    return await db.get_full_job_result(job_id)
