"""
agents/supervisor.py — CrewAI orchestration layer.

Orchestrates:
  1. validator_agent  — structural correctness
  2. anomaly_agent    — statistical logic
  3. repair_agent     — corrective suggestions
  4. report_agent     — final diagnostics

Agents run AFTER the deterministic pipeline completes,
BEFORE the LLM brief is returned to the frontend.

CrewAI agents receive ONLY structured JSON — no DB access, no APIs.
"""

from typing import Dict, Optional

# ── Try CrewAI — fall back to direct function calls if not installed ──────────
try:
    from crewai import Agent, Task, Crew, Process
    CREWAI_AVAILABLE = True
except ImportError:
    CREWAI_AVAILABLE = False
    print("  [Agents] crewai not installed — using direct validation mode")

from streamgraph2.llm import validator_agent
from streamgraph2.llm import anomaly_agent
from streamgraph2.llm import repair_agent
from streamgraph2.llm import report_agent
from streamgraph2.data.config import GROQ_API_KEY, LLM_MODEL


# ── Direct mode (no CrewAI) ───────────────────────────────────

async def _run_direct(job_id: str, pipeline_result: Dict) -> Dict:
    """
    Run agents sequentially without CrewAI orchestration.
    Used as fallback or for testing.
    """
    print("  [Agents] Running in direct mode")

    validation = validator_agent.validate(pipeline_result)
    anomaly    = anomaly_agent.detect_anomalies(pipeline_result)
    repair     = repair_agent.suggest_repairs(validation, anomaly)
    report     = await report_agent.generate_report(job_id, validation, anomaly, repair)

    return {
        "validation": validation,
        "anomaly"   : anomaly,
        "repair"    : repair,
        "report"    : report,
    }


# ── CrewAI mode ───────────────────────────────────────────────

def _build_crew(pipeline_result: Dict) -> "Crew":
    """Build CrewAI crew for pipeline validation."""
    import json
    result_json = json.dumps(pipeline_result, indent=2)

    from crewai import LLM

    # Initialize LLM properly from config
    llm = LLM(
        model=LLM_MODEL,
        temperature=0.2
    )

    # ── Agent definitions ─────────────────────────────────────

    validation_agent = Agent(
        role="Pipeline Validation Specialist",
        goal="Verify structural correctness of computational pipeline output",
        backstory=(
            "You are a rigorous systems analyst who checks computational outputs "
            "for structural completeness and statistical plausibility. "
            "You never hallucinate — you only report what the data shows."
        ),
        llm=llm,
        verbose=False,
    )

    anomaly_detection_agent = Agent(
        role="Statistical Anomaly Detector",
        goal="Identify logical inconsistencies and statistical anomalies in pipeline results",
        backstory=(
            "You are a statistical quality assurance specialist who identifies "
            "patterns that indicate modeling failures. You look for unexpected "
            "distributions, near-zero signals, and clustering failures."
        ),
        llm=llm,
        verbose=False,
    )

    repair_recommendation_agent = Agent(
        role="Pipeline Repair Strategist",
        goal="Suggest concrete corrective actions for detected issues",
        backstory=(
            "You are a senior ML engineer who translates quality issues into "
            "actionable pipeline corrections. Your suggestions are specific, "
            "parametrized, and implementable."
        ),
        llm=llm,
        verbose=False,
    )

    # ── Task definitions ──────────────────────────────────────

    validate_task = Task(
        description=f"""
        Validate this pipeline output for structural correctness.
        
        Check:
        1. Topics detected and have non-zero sizes
        2. News similarity scores are present
        3. Sentiment percentages sum to approximately 100
        4. Volume acceleration is computed
        5. Minimum news count is met
        
        Pipeline output:
        {result_json[:3000]}
        
        Respond ONLY with a JSON object:
        {{"status": "pass|warn|fail", "issues": ["issue1", "issue2"]}}
        """,
        agent=validation_agent,
        expected_output="JSON object with status and issues list",
    )

    anomaly_task = Task(
        description=f"""
        Analyze this pipeline output for statistical anomalies and logical inconsistencies.
        
        Look for:
        1. Single dominant topic (> 80% of posts)
        2. All similarity scores below 0.40
        3. Negative sentiment decreasing during spike (unexpected)
        4. Acceleration ratio near 1.0 despite spike detection
        5. Only one topic returned by clustering
        
        Pipeline output:
        {result_json[:3000]}
        
        Respond ONLY with a JSON object:
        {{"status": "pass|warn|fail", "anomalies": [{{"code": "CODE", "detail": "..."}}]}}
        """,
        agent=anomaly_detection_agent,
        expected_output="JSON object with status and anomalies list",
    )

    repair_task = Task(
        description=f"""
        Based on the validation and anomaly findings, suggest repair actions.
        
        For each issue, suggest one of:
        - rerun_topic_modeling (with params: reduce_min_topic_size_by)
        - rerun_news_fetch (with params: expand_limit_by)
        - lower_similarity_threshold (with params: new_threshold)
        - expand_reddit_enrichment (with params: expand_window_days)
        - check_baseline_data
        
        Respond ONLY with a JSON object:
        {{
          "issue_detected": true|false,
          "repair_required": true|false,
          "suggestions": [{{"action": "...", "params": {{}}, "reason": "..."}}]
        }}
        """,
        agent=repair_recommendation_agent,
        expected_output="JSON object with repair suggestions",
    )

    return Crew(
        agents=[validation_agent, anomaly_detection_agent, repair_recommendation_agent],
        tasks=[validate_task, anomaly_task, repair_task],
        process=Process.sequential,
        verbose=False,
    )


async def run_supervisor(job_id: str, pipeline_result: Dict) -> Dict:
    """
    Main entry point. Runs agent supervision over pipeline output.
    Uses CrewAI if available, otherwise direct mode.
    """
    print("  [Agents] Supervisor starting")

    if not CREWAI_AVAILABLE:
        return await _run_direct(job_id, pipeline_result)

    # CrewAI mode
    try:
        import json
        crew   = _build_crew(pipeline_result)
        output = crew.kickoff()

        # Parse agent outputs (CrewAI returns raw text — parse JSON blocks)
        def _safe_parse(text: str) -> dict:
            try:
                start = text.find("{")
                end   = text.rfind("}") + 1
                return json.loads(text[start:end])
            except Exception:
                return {}

        task_outputs = output.tasks_output if hasattr(output, "tasks_output") else []
        validation = _safe_parse(task_outputs[0].raw if len(task_outputs) > 0 else "{}")
        anomaly    = _safe_parse(task_outputs[1].raw if len(task_outputs) > 1 else "{}")
        repair_out = _safe_parse(task_outputs[2].raw if len(task_outputs) > 2 else "{}")

        # Fallback to direct for report generation (needs DB access)
        validation = validation or validator_agent.validate(pipeline_result)
        anomaly    = anomaly    or anomaly_agent.detect_anomalies(pipeline_result)
        repair_out = repair_out or repair_agent.suggest_repairs(validation, anomaly)
        report     = await report_agent.generate_report(job_id, validation, anomaly, repair_out)

        return {
            "mode"      : "crewai",
            "validation": validation,
            "anomaly"   : anomaly,
            "repair"    : repair_out,
            "report"    : report,
        }

    except Exception as e:
        print(f"  [Agents] CrewAI failed ({e}) — falling back to direct mode")
        return await _run_direct(job_id, pipeline_result)
