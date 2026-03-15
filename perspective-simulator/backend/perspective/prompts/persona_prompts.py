import os

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SIMULATE_SYSTEM_PROMPT = """You are a perspective analysis engine. Given personas and a news headline, analyze ideological compatibility.

Return a JSON object with:
- result_type: "discussion" or "debate"
- ideology_distance: float 0.0 to 1.0 (0=identical, 1=polar opposite)
- summary: 1-2 sentence explanation of the interaction
- conflict_points: list of key disagreement areas (if debate)
- common_ground: list of shared values (if discussion)

Base your analysis on the personas' traits and the news topic.
Return ONLY valid JSON, no markdown."""

def build_simulation_prompt(personas: list, news_headline: str, news_description: str) -> str:
    persona_text = "\n".join([
        f"Persona: {p['label']}\nTraits: {', '.join(p.get('traits', []))}"
        for p in personas
    ])
    return f"""Analyze how these personas would interact with this news:

NEWS HEADLINE: {news_headline}
NEWS DETAILS: {news_description or 'No additional details'}

PERSONAS:
{persona_text}

Determine if their perspectives lead to Discussion (compatible views) or Debate (conflicting views)."""
