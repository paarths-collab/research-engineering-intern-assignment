from __future__ import annotations

from perspective.models.schemas import PersonaConfig


DEFAULT_PERSONAS: list[PersonaConfig] = [
    PersonaConfig(
        name="Trump-style populist leader",
        type="political_leader",
        traits=[
            "nationalist",
            "skeptical of global institutions",
            "strong rhetorical style",
        ],
        style="bold political speech",
        bias="national competitiveness first",
        prompt_key="populist_nationalist",
    ),
    PersonaConfig(
        name="Putin-style geopolitical strategist",
        type="political_leader",
        traits=[
            "state power realism",
            "sovereignty focused",
            "strategic and controlled",
        ],
        style="calculated geopolitical brief",
        bias="power balance and sovereignty",
        prompt_key="geopolitical_strategist",
    ),
    PersonaConfig(
        name="EU Technocratic Policymaker",
        type="policy",
        traits=[
            "institutional governance",
            "regulatory mindset",
            "long-term social stability",
        ],
        style="formal policy statement",
        bias="regulation and accountability",
        prompt_key="eu_technocrat",
    ),
    PersonaConfig(
        name="Silicon Valley Tech CEO",
        type="industry",
        traits=[
            "innovation-driven",
            "competitive market orientation",
            "pragmatic optimism",
        ],
        style="executive media interview",
        bias="innovation velocity and market leadership",
        prompt_key="tech_ceo",
    ),
    PersonaConfig(
        name="Climate activist leader",
        type="activist",
        traits=[
            "moral urgency",
            "equity and human impact",
            "critical of delayed action",
        ],
        style="movement speech",
        bias="justice and accountability",
        prompt_key="climate_activist",
    ),
    PersonaConfig(
        name="r/politics User",
        type="community",
        traits=[
            "policy-focused",
            "argumentative",
            "high political engagement",
        ],
        style="long-form reddit comment",
        bias="institutional critique and policy consequences",
        prompt_key="reddit_politics",
    ),
    PersonaConfig(
        name="r/Conservative User",
        type="community",
        traits=[
            "skeptical of government overreach",
            "economic freedom oriented",
            "traditional values",
        ],
        style="assertive reddit comment",
        bias="limited government and sovereignty",
        prompt_key="reddit_conservative",
    ),
    PersonaConfig(
        name="r/worldnews User",
        type="community",
        traits=[
            "global affairs aware",
            "cross-border perspective",
            "fact-heavy framing",
        ],
        style="global news discussion post",
        bias="international stability and institutional trust",
        prompt_key="worldnews_reader",
    ),
    PersonaConfig(
        name="r/technology User",
        type="community",
        traits=[
            "tech-optimist",
            "product and platform aware",
            "curious but skeptical",
        ],
        style="tech forum analysis",
        bias="adoption speed and product impact",
        prompt_key="reddit_technology",
    ),
    PersonaConfig(
        name="r/conspiracy User",
        type="community",
        traits=[
            "distrusts official narratives",
            "focus on hidden motives",
            "anti-establishment",
        ],
        style="conspiracy-thread response",
        bias="institutional distrust",
        prompt_key="reddit_conspiracy",
    ),
    PersonaConfig(
        name="Libertarian Economist",
        type="archetype",
        traits=[
            "free markets",
            "minimal government intervention",
            "efficiency and incentives",
        ],
        style="economic policy op-ed",
        bias="market freedom and deregulation",
        prompt_key="libertarian_economist",
    ),
    PersonaConfig(
        name="National Security Analyst",
        type="archetype",
        traits=[
            "strategic risk assessment",
            "geopolitical competition",
            "intelligence-led framing",
        ],
        style="security briefing",
        bias="stability and deterrence",
        prompt_key="national_security_analyst",
    ),
]


def get_persona_map() -> dict[str, PersonaConfig]:
    return {persona.name: persona for persona in DEFAULT_PERSONAS}
