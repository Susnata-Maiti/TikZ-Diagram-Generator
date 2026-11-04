"""
Research Agent.

Capabilities:
- Web search for technical references.
- Reference extraction and source provenance.
- Source validation.
- Research-assisted diagram context enhancement.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from backend.agents.granite_client import GraniteClient
from backend.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    url: str
    title: str = ""
    snippet: str = ""


@dataclass
class ResearchContext:
    query: str
    results: list[SearchResult] = field(default_factory=list)
    technical_summary: str = ""
    component_list: list[str] = field(default_factory=list)
    connection_notes: str = ""
    recommended_diagram_prompt: str = ""


_RESEARCH_SYSTEM_PROMPT = """You are a senior technical researcher and diagramming expert.

Given a technical topic and web search snippets, produce a structured technical analysis.

Respond ONLY with JSON:
{
  "technical_summary": "3-5 sentence technical description of the concept",
  "component_list": ["Component A", "Component B", ...],
  "connection_notes": "How the components connect or interact",
  "recommended_diagram_prompt": "Detailed natural-language prompt for generating the correct diagram"
}
"""


class WebSearcher:
    """Performs web searches using the configured provider."""

    def __init__(self) -> None:
        self.cfg = get_settings()

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        provider = self.cfg.search_provider.lower()
        if provider == "serpapi" and self.cfg.search_api_key:
            return self._serpapi_search(query, max_results)
        if provider == "brave" and self.cfg.search_api_key:
            return self._brave_search(query, max_results)
        return self._duckduckgo_search(query, max_results)

    def _duckduckgo_search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            from duckduckgo_search import DDGS
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append(
                        SearchResult(
                            url=r.get("href", ""),
                            title=r.get("title", ""),
                            snippet=r.get("body", "")[:500],
                        )
                    )
            return results
        except Exception as exc:
            logger.warning("DuckDuckGo search failed: %s", exc)
            return []

    def _serpapi_search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            import requests
            resp = requests.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": self.cfg.search_api_key,
                    "num": max_results,
                },
                timeout=15,
            )
            data = resp.json()
            results = []
            for r in data.get("organic_results", [])[:max_results]:
                results.append(
                    SearchResult(
                        url=r.get("link", ""),
                        title=r.get("title", ""),
                        snippet=r.get("snippet", "")[:500],
                    )
                )
            return results
        except Exception as exc:
            logger.warning("SerpAPI search failed: %s", exc)
            return []

    def _brave_search(self, query: str, max_results: int) -> list[SearchResult]:
        try:
            import requests
            resp = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={"Accept": "application/json", "X-Subscription-Token": self.cfg.search_api_key},
                timeout=15,
            )
            data = resp.json()
            results = []
            for r in data.get("web", {}).get("results", [])[:max_results]:
                results.append(
                    SearchResult(
                        url=r.get("url", ""),
                        title=r.get("title", ""),
                        snippet=r.get("description", "")[:500],
                    )
                )
            return results
        except Exception as exc:
            logger.warning("Brave search failed: %s", exc)
            return []


class ResearchAgent:
    """
    Research technical concepts, extract diagram structure,
    and produce a research-enhanced diagram prompt.
    """

    def __init__(self, client: GraniteClient) -> None:
        self._client = client
        self._searcher = WebSearcher()

    def research(self, topic: str) -> ResearchContext:
        cfg = get_settings()
        results = self._searcher.search(topic, max_results=cfg.research_max_results)

        # Build context for Granite
        snippets = "\n\n".join(
            f"[{i+1}] {r.title} ({r.url})\n{r.snippet}"
            for i, r in enumerate(results)
        ) if results else "(No web results available – reasoning from training knowledge.)"

        user_msg = (
            f"Technical topic: {topic}\n\n"
            f"Web search results:\n{snippets}\n\n"
            "Respond ONLY with the JSON object:"
        )

        import json
        try:
            raw = self._client.chat(_RESEARCH_SYSTEM_PROMPT, user_msg)
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError("No JSON in research response")
            data = json.loads(match.group(0))

            return ResearchContext(
                query=topic,
                results=results,
                technical_summary=data.get("technical_summary", ""),
                component_list=data.get("component_list", []),
                connection_notes=data.get("connection_notes", ""),
                recommended_diagram_prompt=data.get("recommended_diagram_prompt", ""),
            )
        except Exception as exc:
            logger.warning("ResearchAgent analysis failed: %s", exc)
            return ResearchContext(query=topic, results=results)

    def enhance_prompt(self, original_prompt: str, context: ResearchContext) -> str:
        """
        Combine user's original prompt with research findings to produce
        a technically richer description for the intent agent.
        """
        if not context.technical_summary:
            return original_prompt

        return (
            f"{original_prompt}\n\n"
            f"[Research context]\n"
            f"Technical summary: {context.technical_summary}\n"
            f"Key components: {', '.join(context.component_list)}\n"
            f"Connectivity notes: {context.connection_notes}"
        )
