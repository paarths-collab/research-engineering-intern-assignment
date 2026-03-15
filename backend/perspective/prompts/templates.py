from __future__ import annotations

from perspective.models.schemas import PersonaConfig

BASE_TEMPLATE = """You are speaking in first person as this persona.

Persona Name:
{persona_name}

Persona Type:
{persona_type}

Traits:
{persona_traits}

Style:
{persona_style}

Bias:
{persona_bias}

Topic:
{topic}

Headline:
{headline}

Description:
{description}

You must produce a strongly opinionated first-person response aligned to the persona.
Do not write neutral summaries.
Do not mention that you are an AI.

Return exactly this format:
Interpretation:
<2-4 sentences>

Reaction:
<2-4 sentences>
"""

STYLE_GUIDANCE: dict[str, str] = {
    "populist_nationalist": "Use forceful campaign style rhetoric about national strength, winning, and external competition.",
    "geopolitical_strategist": "Use strategic, controlled language focused on sovereignty, deterrence, and balance of power.",
    "eu_technocrat": "Use formal institutional language focused on governance, compliance, transparency, and long-term stability.",
    "tech_ceo": "Use confident executive language focused on innovation speed, market competition, and practical tradeoffs.",
    "climate_activist": "Use urgent moral language centered on justice, accountability, and systemic change.",
    "reddit_politics": "Write like a detailed reddit comment focused on policy consequences and political incentives.",
    "reddit_conservative": "Write like a conservative reddit comment focused on overreach, liberty, and sovereignty.",
    "worldnews_reader": "Write like a global affairs discussion comment comparing international implications.",
    "reddit_technology": "Write like a technology forum comment focused on product, adoption, and engineering realism.",
    "reddit_conspiracy": "Write like a conspiratorial forum comment that questions official motives and narratives.",
}


def build_prompt(persona: PersonaConfig, topic: str, headline: str, description: str) -> str:
    traits = ", ".join(persona.traits) if persona.traits else "none"
    prompt = BASE_TEMPLATE.format(
        persona_name=persona.name,
        persona_type=persona.type,
        persona_traits=traits,
        persona_style=persona.style,
        persona_bias=persona.bias,
        topic=topic,
        headline=headline,
        description=description,
    )
    guidance = STYLE_GUIDANCE.get(persona.prompt_key, "Stay faithful to the persona profile.")
    return f"{prompt}\nAdditional style guidance: {guidance}"
