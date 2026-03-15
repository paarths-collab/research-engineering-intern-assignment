from __future__ import annotations

import json
import logging
import os
import re
import time
from itertools import combinations
from pathlib import Path

import httpx

from perspective.models.schemas import (
    PerspectiveGraphEdge,
    PerspectiveGraphNode,
    PerspectiveSimulateRequest,
    PerspectiveSimulateResponse,
)
from perspective.personas.default_personas import DEFAULT_PERSONAS, get_persona_map

logger = logging.getLogger("perspective.simulator")


class PerspectiveSimulatorService:
    def __init__(self):
        self.persona_map = get_persona_map()
        self.prompt_personas = _load_prompt_personas()
        self.news_presets_cache: list[dict] = []
        self.news_presets_cached_at: float = 0.0

    def list_personas(self):
        if self.prompt_personas:
            return self.prompt_personas
        return DEFAULT_PERSONAS

    def list_news_presets(self, limit: int = 15) -> list[dict]:
        safe_limit = max(limit, 1)
        cache_ttl_seconds = 300

        if self.news_presets_cache and (time.time() - self.news_presets_cached_at) < cache_ttl_seconds:
            return self.news_presets_cache[:safe_limit]

        live_events = self._fetch_globe_events(limit=max(safe_limit * 2, 20))
        live_presets = _build_presets_from_events(live_events, limit=max(safe_limit * 2, 20))
        cached_presets = _load_cached_news_presets(limit=max(safe_limit * 3, 30))

        merged: list[dict] = []
        seen_labels: set[str] = set()

        for item in [*live_presets, *cached_presets]:
            label = str(item.get("label") or "").strip().lower()
            if not label or label in seen_labels:
                continue
            seen_labels.add(label)
            merged.append(item)
            if len(merged) >= safe_limit:
                break

        if merged:
            self.news_presets_cache = merged
            self.news_presets_cached_at = time.time()
            return merged

        return self.news_presets_cache[:safe_limit] if self.news_presets_cache else []

    def simulate(self, payload: PerspectiveSimulateRequest) -> PerspectiveSimulateResponse:
        base_nodes = [n for n in payload.nodes if n.type in {"persona", "news"}]
        base_node_ids = {n.id for n in base_nodes}
        base_edges: list[PerspectiveGraphEdge] = []

        for e in payload.edges:
            if e.source in base_node_ids and e.target in base_node_ids:
                base_edges.append(
                    PerspectiveGraphEdge(
                        id=e.id,
                        source=e.source,
                        target=e.target,
                        type="smoothstep",
                        animated=True,
                        style=e.style,
                    )
                )

        personas_by_id = {n.id: n for n in base_nodes if n.type == "persona"}
        news_by_id = {n.id: n for n in base_nodes if n.type == "news"}
        globe_events = self._fetch_globe_events(limit=30)

        for news_node in news_by_id.values():
            self._enrich_news_node(news_node, globe_events)

        connected_personas_by_news: dict[str, list[PerspectiveGraphNode]] = {nid: [] for nid in news_by_id}
        for edge in base_edges:
            if edge.source in personas_by_id and edge.target in news_by_id:
                connected_personas_by_news[edge.target].append(personas_by_id[edge.source])

        generated_nodes: list[PerspectiveGraphNode] = []
        generated_edges: list[PerspectiveGraphEdge] = []
        generated_meta: list[dict[str, str]] = []
        generated_modes: set[str] = set()
        overall_summary = "No valid persona-news connections found for simulation."

        for news_id, personas in connected_personas_by_news.items():
            unique_personas = _unique_nodes(personas)
            if len(unique_personas) == 0:
                continue

            if len(unique_personas) == 1:
                persona = unique_personas[0]
                news_node = news_by_id[news_id]
                detailed_reactions = _build_persona_reactions(unique_personas, news_node, "analysis", self.persona_map)
                analysis_rounds = _build_connected_rounds(
                    personas=unique_personas,
                    mode="analysis",
                    reactions=detailed_reactions,
                    round_count=1,
                    persona_map=self.persona_map,
                )
                news_node.data["analysis_summary"] = (
                    f"Analysis view: {persona.data.get('label', 'Selected persona')} is reviewing this headline."
                )
                news_node.data["reactions"] = detailed_reactions
                news_node.data["rounds"] = analysis_rounds

                analysis_id = f"analysis-{news_id}"
                generated_nodes.append(
                    PerspectiveGraphNode(
                        id=analysis_id,
                        type="analysis",
                        position={
                            "x": float(news_node.position.get("x", 0.0)) + 120.0,
                            "y": float(news_node.position.get("y", 0.0)) + 220.0,
                        },
                        data={
                            "label": "Analysis",
                            "newsId": news_id,
                            "personaCount": 1,
                            "summary": news_node.data["analysis_summary"],
                            "reactions": detailed_reactions,
                            "rounds": analysis_rounds,
                        },
                    )
                )

                generated_edges.append(
                    PerspectiveGraphEdge(
                        id=f"e-{news_id}-{analysis_id}",
                        source=news_id,
                        target=analysis_id,
                        type="smoothstep",
                        animated=True,
                        style={"strokeWidth": 2},
                    )
                )
                generated_edges.append(
                    PerspectiveGraphEdge(
                        id=f"e-{persona.id}-{analysis_id}",
                        source=persona.id,
                        target=analysis_id,
                        type="smoothstep",
                        animated=True,
                        style={"strokeWidth": 2},
                    )
                )

                generated_meta.append(
                    {
                        "news_id": news_id,
                        "outcome": "analysis",
                        "persona_count": "1",
                        "distance": "0.000",
                    }
                )
                generated_modes.add("analysis")
                overall_summary = "Normal analysis generated for single persona and single news connection."
                continue

            disagreement = _estimate_disagreement(unique_personas, self.persona_map)
            news_node = news_by_id[news_id]
            discussion_reactions = _build_persona_reactions(unique_personas, news_node, "discussion", self.persona_map)
            debate_reactions = _build_persona_reactions(unique_personas, news_node, "debate", self.persona_map)
            discussion_rounds = _build_connected_rounds(
                personas=unique_personas,
                mode="discussion",
                reactions=discussion_reactions,
                round_count=payload.debate_rounds,
                persona_map=self.persona_map,
            )
            debate_rounds = _build_connected_rounds(
                personas=unique_personas,
                mode="debate",
                reactions=debate_reactions,
                round_count=payload.debate_rounds,
                persona_map=self.persona_map,
            )

            discussion_id = f"discussion-{news_id}"
            generated_nodes.append(
                PerspectiveGraphNode(
                    id=discussion_id,
                    type="discussion",
                    position={
                        "x": float(news_node.position.get("x", 0.0)),
                        "y": float(news_node.position.get("y", 0.0)) + 240.0,
                    },
                    data={
                        "label": "Discussion",
                        "newsId": news_id,
                        "personaCount": len(unique_personas),
                        "ideologicalDistance": round(disagreement, 3),
                        "summary": "Multiple personas are discussing implications from different angles.",
                        "reactions": discussion_reactions,
                        "rounds": discussion_rounds,
                    },
                )
            )

            debate_id = f"debate-{news_id}"
            generated_nodes.append(
                PerspectiveGraphNode(
                    id=debate_id,
                    type="debate",
                    position={
                        "x": float(news_node.position.get("x", 0.0)) + 220.0,
                        "y": float(news_node.position.get("y", 0.0)) + 240.0,
                    },
                    data={
                        "label": "Debate",
                        "newsId": news_id,
                        "personaCount": len(unique_personas),
                        "ideologicalDistance": round(disagreement, 3),
                        "summary": "Competing framings create clear contention across connected personas.",
                        "reactions": debate_reactions,
                        "rounds": debate_rounds,
                    },
                )
            )

            generated_edges.append(
                PerspectiveGraphEdge(
                    id=f"e-{news_id}-{discussion_id}",
                    source=news_id,
                    target=discussion_id,
                    type="smoothstep",
                    animated=True,
                    style={"strokeWidth": 2},
                )
            )
            generated_edges.append(
                PerspectiveGraphEdge(
                    id=f"e-{news_id}-{debate_id}",
                    source=news_id,
                    target=debate_id,
                    type="smoothstep",
                    animated=True,
                    style={"strokeWidth": 2},
                )
            )

            for persona in unique_personas:
                generated_edges.append(
                    PerspectiveGraphEdge(
                        id=f"e-{persona.id}-{discussion_id}",
                        source=persona.id,
                        target=discussion_id,
                        type="smoothstep",
                        animated=True,
                        style={"strokeWidth": 2},
                    )
                )
                generated_edges.append(
                    PerspectiveGraphEdge(
                        id=f"e-{persona.id}-{debate_id}",
                        source=persona.id,
                        target=debate_id,
                        type="smoothstep",
                        animated=True,
                        style={"strokeWidth": 2},
                    )
                )

            generated_meta.append(
                {
                    "news_id": news_id,
                    "outcome": "discussion",
                    "persona_count": str(len(unique_personas)),
                    "distance": f"{disagreement:.3f}",
                }
            )
            generated_meta.append(
                {
                    "news_id": news_id,
                    "outcome": "debate",
                    "persona_count": str(len(unique_personas)),
                    "distance": f"{disagreement:.3f}",
                }
            )
            generated_modes.update({"discussion", "debate"})
            overall_summary = "Generated both discussion and debate views for multi-persona connections."

        result_type = "analysis"
        if "debate" in generated_modes:
            result_type = "debate"
        elif "discussion" in generated_modes:
            result_type = "discussion"

        return PerspectiveSimulateResponse(
            nodes=[*base_nodes, *generated_nodes],
            edges=[*base_edges, *generated_edges],
            generated=generated_meta,
            result_type=result_type,
            summary=overall_summary,
        )

    def _fetch_globe_events(self, limit: int = 20) -> list[dict]:
        base_url = os.getenv("PERSPECTIVE_GLOBE_API_URL", "http://localhost:8000/api/globe")
        target = f"{base_url.rstrip('/')}/events/"

        try:
            with httpx.Client(timeout=8.0, follow_redirects=True) as client:
                response = client.get(target, params={"limit": max(limit, 1)})
            response.raise_for_status()
            payload = response.json() or {}
            events = payload.get("events") if isinstance(payload, dict) else []
            if isinstance(events, list):
                return [event for event in events if isinstance(event, dict)]
        except Exception as exc:
            logger.warning("Failed to fetch Globe events for Perspective: %s", exc)

        return []

    def _enrich_news_node(self, node: PerspectiveGraphNode, globe_events: list[dict]) -> None:
        if not globe_events:
            return

        label = str(node.data.get("label") or "").strip()
        description = str(node.data.get("description") or "").strip()
        query_text = f"{label} {description}".strip()
        if not query_text:
            return

        ranked = []
        for event in globe_events:
            score = _event_relevance_score(query_text, event)
            if score <= 0:
                continue
            ranked.append((score, event))

        ranked.sort(key=lambda item: item[0], reverse=True)
        selected_events = [event for _, event in ranked[:3]]
        if not selected_events:
            selected_events = globe_events[:2]

        reports: list[dict] = []
        event_summaries: list[str] = []

        for event in selected_events:
            event_title = str(event.get("title") or "Global event").strip()
            summary = str(event.get("summary") or "").strip()
            implications = [str(item).strip() for item in (event.get("strategic_implications") or []) if str(item).strip()]
            event_summaries.append(
                f"{event_title}: {summary}" + (f" Implications: {'; '.join(implications[:3])}." if implications else "")
            )

            for source in _normalize_news_sources(event.get("news_sources") or []):
                reports.append(
                    {
                        "event_id": str(event.get("id") or "").strip(),
                        "event_title": event_title,
                        "title": source.get("title"),
                        "description": source.get("description"),
                        "source_name": source.get("source_name"),
                        "link": source.get("link"),
                        "pub_date": source.get("pub_date"),
                    }
                )

        if reports:
            deduped_reports: list[dict] = []
            seen_keys: set[str] = set()
            for report in reports:
                key = f"{report.get('title','')}|{report.get('link','')}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                deduped_reports.append(report)
            reports = deduped_reports[:12]

        if event_summaries:
            enrichment = " ".join(event_summaries[:2]).strip()
            if description:
                node.data["description"] = f"{description} | Globe: {enrichment}"[:1200]
            else:
                node.data["description"] = f"Globe: {enrichment}"[:1200]

        node.data["globe_reports"] = reports
        node.data["globe_events"] = [
            {
                "event_id": str(event.get("id") or "").strip(),
                "title": str(event.get("title") or "").strip(),
                "summary": str(event.get("summary") or "").strip(),
                "risk_level": str(event.get("risk_level") or "").strip(),
                "impact_score": event.get("impact_score"),
                "strategic_implications": [
                    str(item).strip()
                    for item in (event.get("strategic_implications") or [])
                    if str(item).strip()
                ],
            }
            for event in selected_events
        ]


def _unique_nodes(nodes: list[PerspectiveGraphNode]) -> list[PerspectiveGraphNode]:
    out: list[PerspectiveGraphNode] = []
    seen: set[str] = set()
    for n in nodes:
        if n.id in seen:
            continue
        seen.add(n.id)
        out.append(n)
    return out


def _estimate_disagreement(personas: list[PerspectiveGraphNode], persona_map: dict) -> float:
    if len(personas) < 2:
        return 0.0

    distances: list[float] = []
    for left, right in combinations(personas, 2):
        lt = _extract_traits(left, persona_map)
        rt = _extract_traits(right, persona_map)

        set_l = set(lt)
        set_r = set(rt)
        union_size = max(len(set_l | set_r), 1)
        overlap = len(set_l & set_r)
        trait_distance = 1.0 - (overlap / union_size)

        orientation_distance = min(abs(_orientation_score(lt) - _orientation_score(rt)) / 8.0, 1.0)
        distances.append((trait_distance * 0.65) + (orientation_distance * 0.35))

    return sum(distances) / len(distances)


def _extract_traits(node: PerspectiveGraphNode, persona_map: dict) -> list[str]:
    raw_traits = node.data.get("traits") or []
    if isinstance(raw_traits, str):
        raw_traits = [t.strip() for t in raw_traits.split(",") if t.strip()]

    traits = [str(t).strip().lower() for t in raw_traits if str(t).strip()]
    name = str(node.data.get("name") or "").strip()
    mapped = persona_map.get(name)
    if mapped:
        traits.extend([str(t).strip().lower() for t in mapped.traits])
    return list(dict.fromkeys(traits))


def _orientation_score(traits: list[str]) -> float:
    score = 0.0
    joined = " ".join(traits)

    positive_markers = [
        "institutional",
        "regulatory",
        "global",
        "collective",
        "social stability",
        "accountability",
        "equity",
    ]
    negative_markers = [
        "nationalist",
        "anti-establishment",
        "skeptical",
        "limited government",
        "market",
        "sovereignty",
        "traditional",
    ]

    for marker in positive_markers:
        if marker in joined:
            score += 1.0
    for marker in negative_markers:
        if marker in joined:
            score -= 1.0

    return score


def _load_prompt_personas() -> list[dict]:
    prompts_file = Path(__file__).resolve().parent.parent / "prompts" / "persona_prompts.json"
    if not prompts_file.exists():
        return []

    try:
        data = json.loads(prompts_file.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to parse persona prompt file: %s", prompts_file)
        return []

    if not isinstance(data, list):
        return []

    personas: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        subreddit = str(item.get("subreddit") or "").strip()
        persona_prompt = str(item.get("persona_prompt") or "").strip()
        if not subreddit or not persona_prompt:
            continue
        personas.append(
            {
                "name": subreddit,
                "type": "community",
                "traits": [],
                "style": "subreddit persona prompt",
                "bias": "",
                "prompt_key": "subreddit_persona",
                "subreddit": subreddit,
                "persona_prompt": persona_prompt,
            }
        )

    return personas


def _normalize_news_sources(news_sources: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for source in news_sources:
        if not isinstance(source, dict):
            continue
        title = str(source.get("title") or "").strip()
        if not title:
            continue
        normalized.append(
            {
                "title": title,
                "description": str(
                    source.get("description")
                    or source.get("summary")
                    or source.get("snippet")
                    or ""
                ).strip(),
                "source_name": str(source.get("source_name") or source.get("source") or "Unknown").strip(),
                "link": str(source.get("link") or source.get("url") or "").strip(),
                "pub_date": str(source.get("pub_date") or source.get("published_at") or "").strip(),
            }
        )
    return normalized


def _build_presets_from_events(events: list[dict], limit: int) -> list[dict]:
    presets: list[dict] = []
    for event in events[:limit]:
        sources = _normalize_news_sources(event.get("news_sources") or [])
        implications = [str(item).strip() for item in (event.get("strategic_implications") or []) if str(item).strip()]
        summary = str(event.get("summary") or "").strip()

        description_parts = []
        if summary:
            description_parts.append(summary)
        if implications:
            description_parts.append(f"Implications: {'; '.join(implications[:3])}")

        label = str(event.get("title") or "Global Event").strip()
        if not label:
            continue

        presets.append(
            {
                "label": label,
                "description": " | ".join(description_parts) if description_parts else "No summary available.",
                "event_id": str(event.get("id") or "").strip(),
                "risk_level": str(event.get("risk_level") or "").strip(),
                "impact_score": event.get("impact_score"),
                "strategic_implications": implications,
                "reports": sources,
            }
        )
    return presets


def _load_cached_news_presets(limit: int = 30) -> list[dict]:
    cache_path = Path(__file__).resolve().parents[3] / "data" / "ai_cache.json"
    if not cache_path.exists():
        return []

    try:
        cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to parse cached Globe headlines from %s", cache_path)
        return []

    if not isinstance(cache_payload, dict):
        return []

    presets: list[dict] = []

    for value in cache_payload.values():
        if not isinstance(value, dict):
            continue

        event_id = ""
        event_title = ""
        event_summary = ""

        if isinstance(value.get("aggregated_context"), dict):
            event_ctx = value.get("aggregated_context") or {}
            event = event_ctx.get("event") or {}
            event_id = str(event.get("event_id") or "").strip()
            event_title = str(event.get("title") or "").strip()
            event_summary = str(event.get("summary") or "").strip()

        articles = []
        if isinstance(value.get("news_context"), dict):
            articles = value.get("news_context", {}).get("articles") or []
        elif isinstance(value.get("articles_used"), list):
            articles = value.get("articles_used") or []

        normalized_articles = _normalize_news_sources(articles if isinstance(articles, list) else [])
        for article in normalized_articles:
            title = str(article.get("title") or "").strip()
            if not title:
                continue

            description_parts = []
            if article.get("description"):
                description_parts.append(str(article.get("description")))
            if event_title:
                description_parts.append(f"Context: {event_title}")
            elif event_summary:
                description_parts.append(f"Context: {event_summary}")

            presets.append(
                {
                    "label": title,
                    "description": " | ".join(description_parts)[:1200],
                    "event_id": event_id,
                    "risk_level": "",
                    "impact_score": None,
                    "strategic_implications": [],
                    "reports": [article],
                }
            )

            if len(presets) >= limit:
                return presets

    return presets


def _event_relevance_score(query_text: str, event: dict) -> float:
    query_tokens = _tokenize(query_text)
    if not query_tokens:
        return 0.0

    event_parts = [
        str(event.get("title") or ""),
        str(event.get("summary") or ""),
        " ".join(str(item) for item in (event.get("strategic_implications") or [])),
    ]

    for source in _normalize_news_sources(event.get("news_sources") or [])[:8]:
        event_parts.append(source.get("title") or "")
        event_parts.append(source.get("description") or "")

    event_tokens = _tokenize(" ".join(event_parts))
    if not event_tokens:
        return 0.0

    overlap = len(query_tokens & event_tokens)
    if overlap == 0:
        return 0.0

    return overlap / max(len(query_tokens), 1)


def _tokenize(text: str) -> set[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "about",
        "news",
        "event",
        "report",
    }
    return {token for token in raw_tokens if len(token) > 2 and token not in stop_words}


def _build_persona_reactions(
    personas: list[PerspectiveGraphNode],
    news_node: PerspectiveGraphNode,
    mode: str,
    persona_map: dict,
) -> list[dict]:
    news_title = str(news_node.data.get("label") or "this event").strip()
    news_summary = str(news_node.data.get("description") or "").strip()
    reports = news_node.data.get("globe_reports") or []

    reactions: list[dict] = []
    for persona in personas:
        persona_name = str(persona.data.get("label") or persona.data.get("name") or persona.id).strip()
        traits = _extract_traits(persona, persona_map)
        persona_prompt = str(persona.data.get("description") or persona.data.get("persona_prompt") or "").strip()
        reaction = _generate_persona_reaction_via_groq(
            persona_name=persona_name,
            persona_traits=traits,
            persona_prompt=persona_prompt,
            mode=mode,
            news_title=news_title,
            news_summary=news_summary,
            reports=reports,
        )

        reactions.append(
            {
                "personaId": persona.id,
                "persona": persona_name,
                "mode": mode,
                "reaction": reaction,
            }
        )

    return reactions


def _generate_persona_reaction_via_groq(
    persona_name: str,
    persona_traits: list[str],
    persona_prompt: str,
    mode: str,
    news_title: str,
    news_summary: str,
    reports: list[dict],
) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("PERSPECTIVE_GROQ_MODEL", "openai/gpt-oss-120b")
    endpoint = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

    trait_text = ", ".join(persona_traits[:8]) if persona_traits else "no explicit traits provided"
    report_lines = []
    for report in (reports or [])[:6]:
        if not isinstance(report, dict):
            continue
        title = str(report.get("title") or "").strip()
        source = str(report.get("source_name") or "Unknown source").strip()
        desc = str(report.get("description") or "").strip()
        if not title:
            continue
        line = f"- [{source}] {title}"
        if desc:
            line += f" :: {desc[:220]}"
        report_lines.append(line)

    report_block = "\n".join(report_lines) if report_lines else "- No supporting articles were available in cache."

    mode_instruction = {
        "analysis": "I am giving my solo analysis.",
        "discussion": "I am participating in a discussion and trying to persuade constructively.",
        "debate": "I am in a direct debate and I am aggressively defending my interpretation.",
    }.get(mode, "I am analyzing this event.")

    prompt = f"""You are roleplaying as this persona and MUST answer in first person (I, me, my).

Persona name: {persona_name}
Persona traits: {trait_text}
Persona profile prompt: {persona_prompt or 'N/A'}
Mode: {mode}

News headline:
{news_title}

News context summary:
{news_summary or 'N/A'}

Supporting articles:
{report_block}

Task:
Write a detailed persona reaction in first person that is specific, evidence-linked, and opinionated.

Formatting requirements:
1) Start with one sentence that clearly states my immediate reaction.
2) Then write 3 short paragraphs with concrete reasoning that references the headline and at least 2 supporting articles when available.
3) End with a bullet list titled 'What I would do next' with 3 actionable steps.
4) Keep it between 220 and 420 words.
5) Do NOT break character and do NOT use third person for myself.

Critical requirement:
Use first-person voice throughout (I, my, me)."""

    if api_key:
        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.post(
                    f"{endpoint}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You produce high-fidelity first-person persona analysis grounded in provided evidence.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.35,
                        "max_tokens": 900,
                    },
                )
            resp.raise_for_status()
            content = (
                resp.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if content:
                return content
        except Exception as exc:
            logger.warning("Groq persona reaction generation failed for %s: %s", persona_name, exc)

    fallback_intro = {
        "analysis": "My immediate reaction is cautious but focused: I think this event has deeper second-order effects than the headline alone suggests.",
        "discussion": "My immediate reaction is to engage constructively: I think we can align on facts while still disagreeing on priorities.",
        "debate": "My immediate reaction is blunt: I strongly disagree with the dominant framing and I think it ignores critical risks.",
    }.get(mode, "My immediate reaction is that this headline demands closer scrutiny before anyone jumps to conclusions.")

    source_text = "; ".join(
        [f"{str(r.get('source_name') or 'source')}: {str(r.get('title') or '')}" for r in (reports or [])[:3] if isinstance(r, dict)]
    ) or "no high-confidence supporting sources"

    return (
        f"{fallback_intro}\n\n"
        f"I am reading '{news_title}' through my own lens shaped by {trait_text}. My first priority is to test whether the claim is structurally credible, who benefits from this framing, and where the hidden costs will land. "
        f"I do not treat headlines as neutral: I look for strategic intent, missing context, and signs of narrative amplification.\n\n"
        f"From the available reporting, I anchor my interpretation on {source_text}. I weigh this against the event summary ({news_summary or 'limited summary available'}) and ask whether the evidence supports escalation, de-escalation, or uncertainty. "
        f"If evidence is mixed, I explicitly downgrade confidence and avoid pretending certainty.\n\n"
        f"In practical terms, my position is that this situation should be treated as dynamic, not static. I would keep updating my view as new verified details emerge, and I would separate emotional reaction from operational judgment so my conclusions remain defensible.\n\n"
        "What I would do next\n"
        "- I would track at least three independent sources and note where their claims converge or diverge.\n"
        "- I would identify the highest-impact risk pathway and define one trigger that would force me to revise my position.\n"
        "- I would communicate my stance with explicit confidence levels so decisions are calibrated to uncertainty."
    )


def _build_connected_rounds(
    personas: list[PerspectiveGraphNode],
    mode: str,
    reactions: list[dict],
    round_count: int,
    persona_map: dict,
) -> list[dict]:
    safe_rounds = max(1, min(int(round_count or 1), 20))
    base_reaction_map = {
        str(item.get("persona") or ""): str(item.get("reaction") or "")
        for item in reactions
    }

    opposite_map = _build_opposite_persona_map(personas, persona_map)

    rounds: list[dict] = []
    prev_round_summary = "Initial positions are being established."

    for round_index in range(1, safe_rounds + 1):
        turns = []
        for persona in personas:
            persona_name = str(persona.data.get("label") or persona.data.get("name") or persona.id)
            base = base_reaction_map.get(persona_name, "")
            short_base = base[:420].strip()
            target_name = opposite_map.get(persona_name, persona_name)
            target_base = base_reaction_map.get(target_name, short_base)[:320].strip()

            if round_index == 1:
                question = (
                    f"Given the headline context, how do you justify your position when I see these risks differently?"
                )
                answer = (
                    f"From {target_name}'s side, the response is that their framework prioritizes: {target_base or 'risk control and evidence-based sequencing.'}"
                )
            else:
                connective = (
                    "Building on the previous round"
                    if mode == "discussion"
                    else "Responding directly to the previous round"
                )
                question = (
                    f"{connective}, my counter-question to {target_name} is: how do you address the unresolved tension from prior summary -> {prev_round_summary}?"
                )
                answer = (
                    f"{target_name} answers by refining their claim: {target_base or 'they accept partial uncertainty but defend their priority ordering.'}"
                )

            turn_text = (
                f"My position update: {short_base} "
                f"Counter-question to {target_name}: {question} "
                f"Answer from {target_name}: {answer}"
            )

            turns.append(
                {
                    "persona": persona_name,
                    "target": target_name,
                    "question": question,
                    "answer": answer,
                    "text": turn_text,
                }
            )

        round_summary = _summarize_round(turns, mode, round_index)
        rounds.append(
            {
                "round": round_index,
                "title": f"Round {round_index}",
                "summary": round_summary,
                "turns": turns,
            }
        )
        prev_round_summary = round_summary

    return rounds


def _build_opposite_persona_map(personas: list[PerspectiveGraphNode], persona_map: dict) -> dict[str, str]:
    names = [str(p.data.get("label") or p.data.get("name") or p.id) for p in personas]
    if len(personas) <= 1:
        return {name: name for name in names}

    traits_by_name = {
        str(p.data.get("label") or p.data.get("name") or p.id): _extract_traits(p, persona_map)
        for p in personas
    }
    orient_by_name = {name: _orientation_score(traits_by_name.get(name, [])) for name in names}

    opposite_map: dict[str, str] = {}
    for name in names:
        farthest = None
        farthest_dist = -1.0
        for other in names:
            if other == name:
                continue
            dist = abs(orient_by_name.get(name, 0.0) - orient_by_name.get(other, 0.0))
            if dist > farthest_dist:
                farthest_dist = dist
                farthest = other
        opposite_map[name] = farthest or name

    return opposite_map


def _summarize_round(turns: list[dict], mode: str, round_index: int) -> str:
    persona_names = [str(turn.get("persona") or "") for turn in turns if turn.get("persona")]
    people = ", ".join(persona_names[:4]) if persona_names else "participants"

    if mode == "debate":
        return f"Round {round_index} intensified disagreements between {people}, with sharper challenges on assumptions and risk framing."
    if mode == "discussion":
        return f"Round {round_index} advanced a connected discussion among {people}, clarifying trade-offs and partial common ground."
    return f"Round {round_index} captured structured analysis updates from {people}."
