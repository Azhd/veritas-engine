"""Live check of every primary-source connector (real network calls).

Run from ``backend/``::

    .venv/Scripts/python -m app.connectors.healthcheck          # all connectors
    .venv/Scripts/python -m app.connectors.healthcheck br.ibge  # only some

Each connector gets a claim it should be able to answer; the check reports OK (answered with
evidence), EMPTY (answered, nothing found), FAIL (error or timeout) or DISABLED (missing free
credential). It never sends any AI key: connectors only query public APIs.
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass

from app.connectors.base import BaseGovConnector
from app.connectors.registry import build_connectors
from app.core.config import get_settings
from app.schemas.evidence import EvidenceQuery
from app.services.claim_heuristics import enrich_analysis, heuristic_analysis

#: A claim each source should answer (language hint for the heuristics).
PROBES: dict[str, tuple[str, str]] = {
    "br.camara": ("A Câmara dos Deputados aprovou a reforma tributária.", "pt"),
    "br.senado": ("O Senado Federal aprovou a reforma tributária.", "pt"),
    "br.ibge": ("A inflação no Brasil passou de 10% nos últimos 12 meses.", "pt"),
    "br.legislacao": ("A Lei 12.965/2014 obriga provedores a guardar registros.", "pt"),
    "br.stj_precedentes": ("O STJ decidiu sobre dano moral por inscrição indevida.", "pt"),
    "br.transparencia": ("Deputado recebeu emendas parlamentares em 2024.", "pt"),
    "fr.data_gouv": ("Le taux de chômage en France a doublé depuis 2020.", "fr"),
    "fr.insee": ("Le taux de chômage en France a doublé depuis 2020.", "fr"),
    "fr.legifrance": ("La loi sur la fin de vie a été adoptée en France.", "fr"),
    "fr.judilibre": ("La Cour de cassation a jugé le licenciement abusif.", "fr"),
    "eu.eurlex": ("La directive européenne sur le droit d'auteur a été adoptée en 2019.", "fr"),
    "science.pubmed": ("Vaccines cause autism in children.", "en"),
    "health.who_gho": ("Measles vaccine coverage fell in France.", "en"),
    "geo.gdelt": ("Ukraine and Russia signed a ceasefire this month.", "en"),
    "geo.reliefweb": ("A humanitarian crisis hit Sudan.", "en"),
    "climate.copernicus": ("2023 e 2024 foram recordes de temperatura média global.", "pt"),
    "climate.noaa": ("2023 e 2024 foram recordes de temperatura média global.", "pt"),
    "web.wayback": ("Esta notícia foi apagada: https://www.gov.br/pt-br", "pt"),
    "kb.wikidata": ("Macron é presidente da França.", "pt"),
    "intl.worldbank": ("Unemployment in Argentina rose above 7%.", "en"),
    "eu.eurostat": ("Le chômage en Allemagne a augmenté en 2025.", "fr"),
    "science.crossref": ("A study proved that ivermectin cures COVID-19.", "en"),
    "factcheck.google": ("Vacinas causam autismo.", "pt"),
}


@dataclass
class Result:
    source_id: str
    status: str  # OK | EMPTY | FAIL | DISABLED | NO_PROBE
    seconds: float = 0.0
    count: int = 0
    detail: str = ""


def probe_query(source_id: str) -> EvidenceQuery | None:
    probe = PROBES.get(source_id)
    if probe is None:
        return None
    claim, language = probe
    analysis = enrich_analysis(heuristic_analysis(claim, language), claim)
    return EvidenceQuery(
        keywords=analysis.keywords,
        keywords_en=analysis.keywords_en,
        people=analysis.people,
        topics=analysis.topics,
        topics_en=analysis.topics_en,
        countries=sorted(c.value for c in analysis.country.countries()),
        legal_references=analysis.legal_references,
        urls=analysis.urls,
        years=analysis.years,
        language=analysis.language,
        max_results=3,
    )


async def check(connector: BaseGovConnector) -> Result:
    if not connector.enabled:
        return Result(connector.source_id, "DISABLED", detail=connector.disabled_reason or "")
    query = probe_query(connector.source_id)
    if query is None:
        return Result(connector.source_id, "NO_PROBE", detail="no test claim for this source")
    started = time.perf_counter()
    try:
        await connector.warm_up()  # bulk datasets (STJ, Copernicus) are loaded at startup
        evidence = await connector.search_within_deadline(query)
    except Exception as exc:  # report every failure, keep checking the others
        return Result(
            connector.source_id,
            "FAIL",
            time.perf_counter() - started,
            detail=f"{type(exc).__name__}: {str(exc)[:160]}",
        )
    seconds = time.perf_counter() - started
    if not evidence:
        return Result(connector.source_id, "EMPTY", seconds, detail=PROBES[connector.source_id][0])
    return Result(connector.source_id, "OK", seconds, len(evidence), evidence[0].title[:90])


async def run(only: list[str] | None = None) -> list[Result]:
    connectors, client = build_connectors(get_settings())
    try:
        results = []
        for connector in connectors:  # one at a time: some APIs rate-limit (GDELT, NCBI)
            if only and connector.source_id not in only:
                continue
            results.append(await check(connector))
        return results
    finally:
        await client.aclose()


def report(results: list[Result]) -> str:
    lines = [f"{'source':<20} {'status':<9} {'time':>6} {'items':>5}  detail"]
    for r in results:
        lines.append(f"{r.source_id:<20} {r.status:<9} {r.seconds:>5.1f}s {r.count:>5}  {r.detail}")
    counts = {s: sum(r.status == s for r in results) for s in ("OK", "EMPTY", "FAIL", "DISABLED")}
    lines.append("")
    lines.append(" · ".join(f"{k}: {v}" for k, v in counts.items()))
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results = asyncio.run(run(sys.argv[1:] or None))
    print(report(results))
    return 1 if any(r.status == "FAIL" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
