"""Verdict engine with audience adaptation (Phase 4).

The facts never change with the reader: the same evidence, verdict and confidence feed three
presentations. Two parts:

* ``audience_instructions`` - how the AI writes the explanation for each reader (added to the
  verdict prompt, so adapting costs no extra AI call on free tiers);
* ``build_audience_report`` - deterministic sections computed from the evidence itself:
  timeline, web-archive history, ABNT / APA references, legal references. They work without
  any AI key (citizen mode) and never invent anything that is not in a source.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime

from app.schemas.audience import (
    ArchiveHistory,
    AudienceMode,
    AudienceReport,
    Citation,
    LegalReference,
    TimelineEvent,
    TimelineKind,
)
from app.schemas.evidence import Evidence

# ---------------------------------------------------------------- prompt
AUDIENCE_INSTRUCTIONS = {
    AudienceMode.GENERAL_FAMILY: (
        "Público: famílias e qualquer pessoa, inclusive quem lê pouco. Escreva a explanation em "
        "linguagem simples, empática e direta, sem jargão, em 2 ou 3 parágrafos curtos; use uma "
        "comparação do dia a dia quando ajudar. Em key_points, dê até 3 frases curtas que "
        "respondam 'por que isso é verdadeiro/falso em 1 minuto', prontas para mandar no "
        "WhatsApp. Deixe contradictions vazio."
    ),
    AudienceMode.JOURNALISM_STUDENT: (
        "Público: estudantes de jornalismo e checadores. Na explanation, mostre o raciocínio de "
        "checagem (OSINT): o que cada fonte diz, a data de cada dado, o que confirma e o que "
        "falta confirmar, e como o leitor pode refazer a verificação. Em key_points, até 3 "
        "conclusões verificáveis. Em contradictions, liste as divergências entre fontes (datas, "
        "números ou afirmações que não batem), citando [E1], [E2]; deixe vazio se não houver."
    ),
    AudienceMode.LAW_ACADEMIC: (
        "Público: área jurídica e acadêmica. Na explanation, use linguagem técnica precisa: "
        "identifique leis, artigos, atos da UE (CELEX), teses e súmulas, e para ciência o tipo "
        "de estudo e o nível de evidência (revisão sistemática, meta-análise, ensaio clínico, "
        "estudo observacional), com PMID/DOI quando houver. Não invente artigos de lei nem "
        "números de processo que não estejam nas evidências. Em key_points, até 3 fundamentos "
        "(norma ou estudo + o que estabelece). Em contradictions, divergências entre fontes ou "
        "entre normas, se houver."
    ),
}


def audience_instructions(mode: AudienceMode) -> str:
    return AUDIENCE_INSTRUCTIONS[mode]


# ---------------------------------------------------------------- report
#: Identifier keys that point to a law, EU act, bill or court precedent.
LEGAL_KEYS = ("norma", "celex", "tema", "proposicao", "materia", "cid", "nor", "pourvoi")
_LAW_CONNECTORS = ("br.legislacao", "br.stj_precedentes", "eu.eurlex", "fr.legifrance")
_DATA_CONNECTORS = ("br.ibge", "fr.insee", "health.who_gho", "climate.copernicus", "climate.noaa")


def build_audience_report(
    mode: AudienceMode,
    evidence: Sequence[tuple[str, Evidence]],
    *,
    cited: set[str] | None = None,
    search_terms: Sequence[str] = (),
    key_points: Sequence[str] = (),
    contradictions: Sequence[str] = (),
    accessed: date | None = None,
) -> AudienceReport:
    cited = cited or set()
    accessed = accessed or date.today()
    return AudienceReport(
        mode=mode,
        key_points=[p.strip() for p in key_points if p and p.strip()][:3],
        contradictions=[c.strip() for c in contradictions if c and c.strip()][:3],
        search_terms=list(dict.fromkeys(t for t in search_terms if t))[:10],
        timeline=build_timeline(evidence),
        archive=[a for eid, item in evidence if (a := archive_history(eid, item))],
        citations=[cite(eid, item, accessed) for eid, item in evidence],
        legal_references=legal_references(evidence, cited),
    )


def build_timeline(evidence: Sequence[tuple[str, Evidence]]) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    for eid, item in evidence:
        if item.connector == "web.wayback":
            for key, kind in (
                ("snapshot_first", TimelineKind.ARCHIVE_FIRST),
                ("snapshot_last", TimelineKind.ARCHIVE_LAST),
            ):
                day = _wayback_day(item.identifiers.get(key))
                if day:
                    events.append(
                        TimelineEvent(day=day, kind=kind, title=item.title, evidence_id=eid)
                    )
            continue
        if item.published_at is None:
            continue
        if item.connector in _LAW_CONNECTORS:
            kind = TimelineKind.LAW
        elif item.connector in _DATA_CONNECTORS:
            kind = TimelineKind.DATA
        else:
            kind = TimelineKind.PUBLICATION
        events.append(
            TimelineEvent(day=item.published_at, kind=kind, title=item.title, evidence_id=eid)
        )
    # same day + same kind once (several WHO rows share a date); oldest first
    unique = {(e.day, e.kind, e.evidence_id): e for e in events}
    return sorted(unique.values(), key=lambda e: (e.day, e.evidence_id))[:20]


def archive_history(evidence_id: str, item: Evidence) -> ArchiveHistory | None:
    if item.connector != "web.wayback" or not item.data.get("archived"):
        return None
    data = item.data
    url = item.title.split(": ", 1)[-1] if ": " in item.title else item.url
    return ArchiveHistory(
        evidence_id=evidence_id,
        url=url,
        captures_inspected=int(data.get("captures_inspected") or 0),
        distinct_versions=int(data.get("distinct_versions") or 0),
        content_changed=bool(data.get("content_changed")),
        title_changed=bool(data.get("title_changed")),
        removed_or_redirected=bool(data.get("removed_or_redirected")),
        first_title=data.get("first_title"),
        last_title=data.get("last_title"),
    )


def legal_references(
    evidence: Sequence[tuple[str, Evidence]], cited: set[str]
) -> list[LegalReference]:
    found: list[LegalReference] = []
    for eid, item in evidence:
        for key in LEGAL_KEYS:
            value = item.identifiers.get(key)
            if value:
                found.append(
                    LegalReference(
                        kind=key,
                        value=str(value),
                        title=item.title,
                        url=item.url,
                        evidence_id=eid,
                        cited=eid in cited,
                    )
                )
                break  # one reference per source (e.g. cid + nor of the same Légifrance text)
    found.sort(key=lambda ref: not ref.cited)
    return found


# ---------------------------------------------------------------- references
_PT_MONTHS = ("jan.", "fev.", "mar.", "abr.", "maio", "jun.", "jul.", "ago.", "set.", "out.",
              "nov.", "dez.")  # fmt: skip


def cite(evidence_id: str, item: Evidence, accessed: date) -> Citation:
    level = None
    if item.data.get("retracted"):
        level = "retracted"
    elif item.data.get("high_level_evidence"):
        level = "high_level"
    return Citation(
        evidence_id=evidence_id,
        abnt=abnt_reference(item, accessed),
        apa=apa_reference(item),
        level=level,
    )


def abnt_reference(item: Evidence, accessed: date) -> str:
    """ABNT NBR 6023:2018 for online documents."""
    title = _sentence(item.title)
    year = str(item.published_at.year) if item.published_at else "[s.d.]"
    if item.authors:
        names = [_abnt_author(a) for a in item.authors[:3]]
        head = "; ".join(names) + ("; et al." if len(item.authors) > 3 else "")
        parts = [f"{head.rstrip('.')}. {title}."]  # "ESLICK, G. D." must not end in ".."
        if item.venue:
            parts.append(f"{item.venue},")
        parts.append(f"{year}.")
    else:
        parts = [f"{item.publisher.upper()}. {title}. {year}."]
    doi = item.identifiers.get("doi")
    if doi:
        parts.append(f"DOI: {doi}.")
    parts.append(f"Disponível em: {item.url}.")
    parts.append(f"Acesso em: {accessed.day} {_PT_MONTHS[accessed.month - 1]} {accessed.year}.")
    return " ".join(parts)


def apa_reference(item: Evidence) -> str:
    """APA 7th edition."""
    title = _sentence(item.title)
    year = f"({item.published_at.year})" if item.published_at else "(n.d.)"
    if item.authors:
        names = [_apa_author(a) for a in item.authors[:20]]
        head = names[0] if len(names) == 1 else ", ".join(names[:-1]) + ", & " + names[-1]
        text = f"{head} {year}. {title}."
        if item.venue:
            text += f" {item.venue}."
    else:
        text = f"{item.publisher}. {year}. {title}."
    doi = item.identifiers.get("doi")
    text += f" https://doi.org/{doi}" if doi else f" {item.url}"
    return text


def _sentence(title: str) -> str:
    return title.strip().rstrip(".")


def _name_parts(author: str) -> tuple[str, list[str]]:
    """PubMed style "Taylor LE" or "Luke E. Taylor" -> ("Taylor", ["L", "E"])."""
    author = author.strip()
    parts = author.split()
    if len(parts) >= 2 and re.fullmatch(r"[A-Z]{1,3}", parts[-1]):
        return " ".join(parts[:-1]), list(parts[-1])
    if "," in author:
        last, first = (p.strip() for p in author.split(",", 1))
        return last, [w[0] for w in first.split() if w]
    if len(parts) >= 2:
        return parts[-1], [w[0] for w in parts[:-1]]
    return author, []


def _abnt_author(author: str) -> str:
    last, initials = _name_parts(author)
    return f"{last.upper()}, {' '.join(i + '.' for i in initials)}".rstrip(", ")


def _apa_author(author: str) -> str:
    last, initials = _name_parts(author)
    return f"{last}, {' '.join(i + '.' for i in initials)}".rstrip(", ")


def _wayback_day(timestamp: str | None) -> date | None:
    try:
        return datetime.strptime(str(timestamp)[:8], "%Y%m%d").date()
    except (TypeError, ValueError):
        return None
