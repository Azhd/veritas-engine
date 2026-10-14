"""Fact-checking orchestrator (text claims).

Pipeline:
    1. receive the claim;
    2. identify country context + search terms (LLM, with heuristic fallback);
    3. query the relevant government connectors concurrently;
    4. build the evidence-grounded prompt;
    5. run the analysis through the request's BYOK provider;
    6. return a structured, auditable report.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
from collections.abc import Sequence

from app.connectors.base import BaseGovConnector
from app.core.errors import ConnectorError, ProviderOutputError
from app.engines.base import BaseLLMProvider
from app.engines.prompt_templates.fact_check import (
    CLAIM_ANALYSIS_SYSTEM,
    VERDICT_SYSTEM,
    build_claim_analysis_prompt,
    build_verdict_prompt,
)
from app.schemas.evidence import Evidence, EvidenceQuery
from app.schemas.fact_check import (
    ASSERTIVE_VERDICTS,
    ClaimAnalysis,
    ConnectorFailure,
    CountryContext,
    FactCheckReport,
    LLMVerdict,
    SourceReference,
    Verdict,
)

logger = logging.getLogger(__name__)

#: Upper bound for confidence when the verdict had to be downgraded for lack of citations.
DOWNGRADED_CONFIDENCE_CAP = 0.5


class FactCheckService:
    def __init__(
        self,
        connectors: Sequence[BaseGovConnector],
        *,
        max_results_per_connector: int = 5,
        max_evidence: int = 20,
    ) -> None:
        self.connectors = list(connectors)
        self.max_results_per_connector = max_results_per_connector
        self.max_evidence = max_evidence

    async def check_text(
        self,
        claim: str,
        llm: BaseLLMProvider,
        country_override: CountryContext | None = None,
    ) -> FactCheckReport:
        notes: list[str] = []

        # 2. context + search terms
        analysis = await self._analyze_claim(claim, llm, notes)
        if country_override is not None:
            analysis.country = country_override
        if not analysis.keywords:
            analysis.keywords = heuristic_keywords(claim)

        # 3. evidence retrieval
        evidence, queried, failures = await self.collect_evidence(analysis)
        numbered = [(f"E{i}", item) for i, item in enumerate(evidence, start=1)]

        # 4 + 5. grounded verdict
        llm_verdict = await llm.generate_structured(
            build_verdict_prompt(claim, numbered, analysis.language),
            LLMVerdict,
            system_instruction=VERDICT_SYSTEM,
            temperature=0.0,
        )

        # 6. auditable report (only sources actually retrieved can appear)
        known_ids = {eid for eid, _ in numbered}
        cited = {eid.strip().strip("[]").upper() for eid in llm_verdict.cited_evidence_ids}
        hallucinated = sorted(cited - known_ids)
        if hallucinated:
            notes.append(f"Citações descartadas (não correspondem a evidências): {hallucinated}")
        cited &= known_ids

        verdict, confidence = llm_verdict.verdict, llm_verdict.confidence_score
        if verdict in ASSERTIVE_VERDICTS and not cited:
            downgraded = Verdict.INCONCLUSIVO if numbered else Verdict.SEM_DADOS_SUFICIENTES
            notes.append(
                f"Veredito {verdict.value} rebaixado para {downgraded.value}: "
                "nenhuma fonte oficial recuperada foi citada como base."
            )
            verdict, confidence = downgraded, min(confidence, DOWNGRADED_CONFIDENCE_CAP)

        sources = [
            SourceReference(
                evidence_id=eid,
                title=item.title,
                url=item.url,
                publisher=item.publisher,
                connector=item.connector,
                country=item.country,
                excerpt=item.excerpt,
                retrieved_at=item.retrieved_at,
                cited=eid in cited,
            )
            for eid, item in numbered
        ]
        sources.sort(key=lambda s: not s.cited)  # cited sources first, stable otherwise

        return FactCheckReport(
            claim=claim,
            verdict=verdict,
            confidence_score=confidence,
            primary_sources=sources,
            explanation=llm_verdict.explanation,
            country_context=analysis.country,
            keywords=analysis.keywords,
            connectors_queried=queried,
            connector_failures=failures,
            provider=llm.name.value,
            model=llm.model,
            notes=notes,
        )

    # ------------------------------------------------------------------ steps
    async def _analyze_claim(
        self, claim: str, llm: BaseLLMProvider, notes: list[str]
    ) -> ClaimAnalysis:
        try:
            return await llm.generate_structured(
                build_claim_analysis_prompt(claim),
                ClaimAnalysis,
                system_instruction=CLAIM_ANALYSIS_SYSTEM,
                temperature=0.0,
            )
        except ProviderOutputError:
            # Auth / rate-limit errors propagate; only unusable *output* falls back.
            notes.append("Triagem por LLM falhou; usada detecção heurística de país/termos.")
            return heuristic_analysis(claim)

    async def collect_evidence(
        self, analysis: ClaimAnalysis
    ) -> tuple[list[Evidence], list[str], list[ConnectorFailure]]:
        countries = analysis.country.countries()
        selected = [c for c in self.connectors if c.country in countries]
        query = EvidenceQuery(
            keywords=analysis.keywords,
            people=analysis.people,
            topics=analysis.topics,
            max_results=self.max_results_per_connector,
        )
        results = await asyncio.gather(
            *(c.search_evidence(query) for c in selected), return_exceptions=True
        )

        evidence: list[Evidence] = []
        failures: list[ConnectorFailure] = []
        seen_urls: set[str] = set()
        for connector, result in zip(selected, results, strict=True):
            if isinstance(result, BaseException):
                if not isinstance(result, Exception):
                    raise result  # CancelledError & co. must not be swallowed
                logger.warning("connector %s failed: %s", connector.source_id, result)
                message = (
                    str(result)
                    if isinstance(result, ConnectorError)
                    else f"unexpected error ({type(result).__name__})"
                )
                failures.append(ConnectorFailure(connector=connector.source_id, error=message))
                continue
            for item in result:
                key = f"{item.url}|{item.title}"
                if key not in seen_urls:
                    seen_urls.add(key)
                    evidence.append(item)
        return evidence[: self.max_evidence], [c.source_id for c in selected], failures


# ---------------------------------------------------------------------- heuristics
_BR_MARKERS = (
    "brasil",
    "brasileir",
    "camara dos deputados",
    "senado federal",
    "stf",
    "ibge",
    "sus",
    "lula",
    "bolsonaro",
    "planalto",
    "reais",
    "r$",
    "pib brasileiro",
    "sao paulo",
    "rio de janeiro",
    "congresso nacional",
    "governo federal",
    "deputado",
    "deputada",
    "ministerio",
)
_FR_MARKERS = (
    "france",
    "francais",
    "francaise",
    "assemblee nationale",
    "senat",
    "insee",
    "macron",
    "elysee",
    "matignon",
    "paris",
    "gouvernement",
    "depute",
    "ministere",
    "loi ",
)
_PT_WORDS = {"nao", "que", "de", "do", "da", "os", "as", "um", "uma", "para", "com", "foi", "sao"}
_FR_WORDS = {"le", "la", "les", "des", "est", "une", "pour", "avec", "pas", "ont", "sont", "du"}
_STOPWORDS = (
    _PT_WORDS
    | _FR_WORDS
    | {
        "e",
        "o",
        "a",
        "em",
        "no",
        "na",
        "nos",
        "por",
        "mais",
        "menos",
        "sobre",
        "ao",
        "aos",
        "seu",
        "sua",
        "et",
        "en",
        "au",
        "aux",
        "dans",
        "sur",
        "par",
        "qui",
        "ce",
        "cette",
        "il",
        "elle",
        "ser",
        "ter",
        "tem",
        "teve",
        "ja",
        "isso",
        "este",
        "esta",
        "entre",
        "desde",
        "ano",
        "anos",
    }
)


def _normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


def heuristic_country(claim: str) -> CountryContext:
    text = _normalize(claim)
    br = sum(marker in text for marker in _BR_MARKERS)
    fr = sum(marker in text for marker in _FR_MARKERS)
    if br and fr:
        return CountryContext.AMBOS
    if br or fr:
        return CountryContext.BR if br else CountryContext.FR
    words = set(re.findall(r"[a-z]+", text))
    pt_hits, fr_hits = len(words & _PT_WORDS), len(words & _FR_WORDS)
    if pt_hits > fr_hits:
        return CountryContext.BR
    if fr_hits > pt_hits:
        return CountryContext.FR
    return CountryContext.DESCONHECIDO


def heuristic_keywords(claim: str, limit: int = 5) -> list[str]:
    words = re.findall(r"[\wÀ-ÿ]+", claim.lower())
    seen: list[str] = []
    for word in words:
        if len(word) < 4 or word.isdigit() or _normalize(word) in _STOPWORDS:
            continue
        if word not in seen:
            seen.append(word)
    return sorted(seen, key=len, reverse=True)[:limit]


def heuristic_analysis(claim: str) -> ClaimAnalysis:
    country = heuristic_country(claim)
    return ClaimAnalysis(
        country=country,
        keywords=heuristic_keywords(claim),
        topics=heuristic_keywords(claim),
        language="fr" if country is CountryContext.FR else "pt",
    )
