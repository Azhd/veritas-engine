"""Fact-checking orchestrator (text claims).

Pipeline:
    1. receive the claim;
    2. identify country, knowledge areas and search terms (LLM, with deterministic fallback);
    3. query the relevant primary-source connectors concurrently;
    4. build the evidence-grounded prompt;
    5. run the analysis through the request's BYOK provider;
    6. return a structured, auditable report.

Citizen mode (zero cost): without an AI provider - or when the provider fails (missing/invalid
key, exhausted free-tier quota, offline) - steps 4-5 are skipped and the report carries the raw
official evidence with verdict ``SEM_CHAVE_IA_DADOS_BRUTOS``. The user is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence

from app.connectors.base import BaseGovConnector
from app.core.errors import (
    ConnectorError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderOutputError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    VeritasError,
)
from app.engines.base import BaseLLMProvider
from app.engines.prompt_templates.fact_check import (
    CLAIM_ANALYSIS_SYSTEM,
    VERDICT_SYSTEM,
    build_claim_analysis_prompt,
    build_verdict_prompt,
)
from app.schemas.evidence import DEFAULT_DOMAINS, Country, Domain, Evidence, EvidenceQuery
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
from app.services.claim_heuristics import (
    VAGUE_CLAIM_TIP,
    enrich_analysis,
    heuristic_analysis,
    is_vague,
)

logger = logging.getLogger(__name__)

#: Upper bound for confidence when the verdict had to be downgraded for lack of citations.
DOWNGRADED_CONFIDENCE_CAP = 0.5
#: Max items from broad sources (e.g. PubMed) once dedicated sources already answered.
SECONDARY_RESULTS_CAP = 3
#: Provider failures that switch the request to citizen mode instead of returning an error.
AI_FAILURES = (
    ProviderConfigurationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderUnavailableError,
    ProviderOutputError,
)
FREE_KEYS_HINT = (
    "Para receber um veredito explicado por IA sem pagar nada: crie uma chave gratuita do "
    "Google Gemini em https://aistudio.google.com/apikey ou do Groq em "
    "https://console.groq.com/keys (sem cartão de crédito), ou use um modelo local com Ollama."
)


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
        llm: BaseLLMProvider | None,
        country_override: CountryContext | None = None,
        *,
        notes: list[str] | None = None,
        source_url: str | None = None,
    ) -> FactCheckReport:
        notes = list(notes or [])

        # 2. context + search terms
        if llm is None:
            analysis = heuristic_analysis(claim)
        else:
            try:
                analysis = await self._analyze_claim(claim, llm, notes)
            except AI_FAILURES as exc:
                notes.append(_ai_failure_note(exc))
                llm, analysis = None, heuristic_analysis(claim)
        if country_override is not None:
            analysis.country = country_override
        analysis = enrich_analysis(analysis, claim)
        if source_url and source_url not in analysis.urls:
            # The user-provided origin of the claim is always audited in the web archive.
            urls = [source_url, *analysis.urls][:5]
            domains = list(dict.fromkeys([*analysis.domains, Domain.WEB_HISTORY]))
            analysis = analysis.model_copy(update={"urls": urls, "domains": domains})
        if not source_url and is_vague(claim, analysis.domains):
            notes.insert(0, VAGUE_CLAIM_TIP)

        # 3. evidence retrieval
        evidence, queried, failures = await self.collect_evidence(analysis)
        numbered = [(f"E{i}", item) for i, item in enumerate(evidence, start=1)]
        if llm is None:
            return self._citizen_report(claim, analysis, numbered, queried, failures, notes)

        # 4 + 5. grounded verdict
        try:
            llm_verdict = await llm.generate_structured(
                build_verdict_prompt(claim, numbered, analysis.language),
                LLMVerdict,
                system_instruction=VERDICT_SYSTEM,
                temperature=0.0,
            )
        except AI_FAILURES as exc:
            notes.append(_ai_failure_note(exc))
            return self._citizen_report(claim, analysis, numbered, queried, failures, notes)

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

        sources = _source_refs(numbered, cited)
        sources.sort(key=lambda s: not s.cited)  # cited sources first, stable otherwise
        return FactCheckReport(
            claim=claim,
            verdict=verdict,
            confidence_score=confidence,
            primary_sources=sources,
            explanation=llm_verdict.explanation,
            country_context=analysis.country,
            domains=analysis.domains,
            keywords=analysis.keywords,
            connectors_queried=queried,
            connector_failures=failures,
            ai_used=True,
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
            # Unusable *output* only: the heuristics take over, the LLM still writes the verdict.
            notes.append("Triagem por IA falhou; usada detecção heurística de país/termos.")
            return heuristic_analysis(claim)

    def select_connectors(self, analysis: ClaimAnalysis) -> list[BaseGovConnector]:
        scopes = {*analysis.country.countries(), Country.GLOBAL}
        if Country.FR in scopes:
            scopes.add(Country.EU)
        domains = set(analysis.domains) or set(DEFAULT_DOMAINS)
        if analysis.urls:
            domains.add(Domain.WEB_HISTORY)
        return [
            c
            for c in self.connectors
            if c.enabled and c.country in scopes and (c.domains & domains)
        ]

    async def collect_evidence(
        self, analysis: ClaimAnalysis
    ) -> tuple[list[Evidence], list[str], list[ConnectorFailure]]:
        selected = self.select_connectors(analysis)
        query = EvidenceQuery(
            keywords=analysis.keywords,
            keywords_en=analysis.keywords_en,
            people=analysis.people,
            topics=analysis.topics,
            topics_en=analysis.topics_en,
            countries=sorted(c.value for c in analysis.country.countries()),
            legal_references=analysis.legal_references,
            urls=analysis.urls,
            max_results=self.max_results_per_connector,
        )
        results = await asyncio.gather(
            *(c.search_evidence(query) for c in selected), return_exceptions=True
        )

        failures: list[ConnectorFailure] = []
        dedicated: list[list[Evidence]] = []
        secondary: list[list[Evidence]] = []
        domains = set(analysis.domains) or set(DEFAULT_DOMAINS)
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
            # Sources dedicated to the claim's areas (e.g. Copernicus for a climate claim) come
            # first; broad sources that merely overlap (e.g. PubMed) come after them.
            (dedicated if connector.domains <= domains else secondary).append(result)
        if any(dedicated):
            secondary = [items[:SECONDARY_RESULTS_CAP] for items in secondary]

        evidence: list[Evidence] = []
        seen: set[str] = set()
        for item in (item for items in [*dedicated, *secondary] for item in items):
            key = f"{item.url}|{item.title}"
            if key not in seen:
                seen.add(key)
                evidence.append(item)
        return evidence[: self.max_evidence], [c.source_id for c in selected], failures

    # ------------------------------------------------------------------ citizen mode
    def _citizen_report(
        self,
        claim: str,
        analysis: ClaimAnalysis,
        numbered: list[tuple[str, Evidence]],
        queried: list[str],
        failures: list[ConnectorFailure],
        notes: list[str],
    ) -> FactCheckReport:
        notes.append(FREE_KEYS_HINT)
        return FactCheckReport(
            claim=claim,
            verdict=Verdict.SEM_CHAVE_IA_DADOS_BRUTOS,
            confidence_score=0.0,
            primary_sources=_source_refs(numbered, cited=set()),
            explanation=citizen_explanation(len(numbered), analysis.language),
            country_context=analysis.country,
            domains=analysis.domains,
            keywords=analysis.keywords,
            connectors_queried=queried,
            connector_failures=failures,
            ai_used=False,
            provider="nenhum",
            model="nenhum",
            notes=notes,
        )


def citizen_explanation(count: int, language: str) -> str:
    if language == "fr":
        if not count:
            return (
                "Mode citoyen (sans IA) : aucune source officielle n'a été trouvée pour cette "
                "affirmation. Essayez d'autres mots-clés ou ajoutez une clé d'IA gratuite."
            )
        return (
            f"Mode citoyen (sans IA) : voici {count} source(s) officielle(s) trouvée(s). "
            "Aucun verdict automatique n'a été produit : lisez les extraits et ouvrez les liens "
            "officiels pour vérifier vous-même."
        )
    if not count:
        return (
            "Modo cidadão (sem IA): nenhuma fonte oficial foi encontrada para esta afirmação. "
            "Tente outras palavras-chave ou adicione uma chave de IA gratuita."
        )
    return (
        f"Modo cidadão (sem IA): encontramos {count} fonte(s) oficial(is) relacionada(s). "
        "Nenhum veredito automático foi gerado: leia os trechos e abra os links oficiais "
        "abaixo para conferir você mesmo."
    )


def _ai_failure_note(exc: VeritasError) -> str:
    logger.warning("AI provider failed, falling back to citizen mode: %s", exc.message)
    return f"IA indisponível ({exc.message.rstrip('.')}). Exibindo os dados oficiais brutos."


def _source_refs(numbered: list[tuple[str, Evidence]], cited: set[str]) -> list[SourceReference]:
    return [
        SourceReference(
            evidence_id=eid,
            title=item.title,
            url=item.url,
            publisher=item.publisher,
            connector=item.connector,
            country=item.country,
            excerpt=item.excerpt,
            authors=item.authors,
            venue=item.venue,
            published_at=item.published_at,
            identifiers=item.identifiers,
            retrieved_at=item.retrieved_at,
            cited=eid in cited,
        )
        for eid, item in numbered
    ]
