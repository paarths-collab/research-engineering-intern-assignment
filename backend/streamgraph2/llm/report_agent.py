"""
agents/report_agent.py — Diagnostic summary generator.

Synthesises all agent findings into a final diagnostic record.
Stores in agent_diagnostics table.
Determines if output is production-ready.
"""

from typing import Dict
from streamgraph2.data import db


def _confidence_score(validation: Dict, anomaly: Dict, repair: Dict) -> float:
    """
    Simple rule-based confidence score 0–1.
    Not ML — deterministic heuristic.
    """
    score = 1.0

    if validation.get("status") == "fail":
        score -= 0.5
    elif validation.get("status") == "warn":
        score -= 0.2

    if anomaly.get("status") == "fail":
        score -= 0.3
    elif anomaly.get("status") == "warn":
        score -= 0.1

    n_suggestions = len(repair.get("suggestions", []))
    score -= min(n_suggestions * 0.05, 0.2)

    return max(round(score, 2), 0.0)


async def generate_report(
    job_id: str,
    validation: Dict,
    anomaly: Dict,
    repair: Dict,
) -> Dict:
    """
    Build diagnostic report and persist to DB.
    Returns report dict.
    """
    conf    = _confidence_score(validation, anomaly, repair)
    ready   = conf >= 0.5 and not repair.get("repair_required", False)

    report = {
        "confidence_score"    : conf,
        "production_ready"    : ready,
        "validation_status"   : validation.get("status"),
        "anomaly_status"      : anomaly.get("status"),
        "issues"              : validation.get("issues", []),
        "anomalies"           : [a["code"] for a in anomaly.get("anomalies", [])],
        "repair_suggestions"  : repair.get("suggestions", []),
        "overall_assessment"  : repair.get("overall_assessment"),
    }

    # Persist each agent's findings separately for traceability
    await db.save_diagnostic(job_id, "validator",        validation.get("status", "fail"), validation)
    await db.save_diagnostic(job_id, "anomaly_detector", anomaly.get("status", "fail"),    anomaly)
    await db.save_diagnostic(job_id, "repair",           "pass",                           repair)
    await db.save_diagnostic(job_id, "report",           "pass" if ready else "warn",      report)

    print(
        f"  [Agents] Confidence: {conf:.2f} | "
        f"Ready: {ready} | "
        f"Assessment: {repair.get('overall_assessment')}"
    )

    return report
