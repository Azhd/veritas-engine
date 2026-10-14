"""Legal and justice primary sources.

* Legislação Federal (BR) - Senado Federal open data (``/dadosabertos/legislacao``), the federal
  norms catalog also published by the Planalto. Looked up by explicit citation (type/number/year).
* STJ precedentes qualificados - official open dataset (CSV) with repetitive-appeal themes, the
  binding theses, originated *súmulas* and links to STF *repercussão geral* themes.
* EUR-Lex (EU) - Publications Office SPARQL endpoint (Cellar).
* Judilibre / Cour de cassation (FR) via PISTE - requires PISTE OAuth credentials.

Known limitation: the STF has no open jurisprudence API; STF *repercussão geral* themes are
reached through the STJ dataset's cross references.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from app.connectors.base import BaseGovConnector, truncate
from app.connectors.br_gov import normalize, parse_br_date
from app.connectors.piste import PisteAuth
from app.core.config import Settings
from app.schemas.evidence import Country, Domain, Evidence, EvidenceQuery

# =====================================================================================
# Brazilian federal legislation (Senado Federal / Planalto)
# =====================================================================================


@dataclass(frozen=True, slots=True)
class LegalReference:
    tipo: str  # Senado code: LEI, LCP, DEL, DEC, MPV, EMC
    numero: str
    ano: int | None

    @property
    def label(self) -> str:
        names = {
            "LEI": "Lei",
            "LCP": "Lei Complementar",
            "DEL": "Decreto-Lei",
            "DEC": "Decreto",
            "MPV": "Medida Provisória",
            "EMC": "Emenda Constitucional",
        }
        suffix = f"/{self.ano}" if self.ano else ""
        return f"{names.get(self.tipo, self.tipo)} {self.numero}{suffix}"


# Order matters: longer names first so "lei complementar" is not read as "lei".
_TYPE_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"lei\s+complementar|\blcp?\b", "LCP"),
    (r"decreto[\s-]+lei|\bdl\b", "DEL"),
    (r"medida\s+provis[oó]ria|\bmpv?\b", "MPV"),
    (r"emenda\s+constitucional|\bec\b", "EMC"),
    (r"decreto", "DEC"),
    (r"\blei\b", "LEI"),
)
_REFERENCE_RE = re.compile(
    r"(?P<tipo>" + "|".join(p for p, _ in _TYPE_PATTERNS) + r")"
    r"\s*(?:n[º°o]?\.?\s*|n[uú]mero\s*)?"
    r"(?P<numero>\d{1,3}(?:\.\d{3})+|\d{1,6})"
    r"(?:\s*/\s*(?P<ano_curto>\d{4})"
    r"|,?\s*de\s+(?:\d{1,2}º?\s+de\s+[a-zç]+\s+de\s+)?(?P<ano>\d{4}))?",
    re.IGNORECASE,
)


def parse_legal_references(texts: list[str]) -> list[LegalReference]:
    """Extract Brazilian federal norm citations such as 'Lei nº 12.965/2014'."""
    found: list[LegalReference] = []
    for text in texts:
        for match in _REFERENCE_RE.finditer(text or ""):
            raw_type = match.group("tipo").lower()
            tipo = next(code for pattern, code in _TYPE_PATTERNS if re.fullmatch(pattern, raw_type))
            ano = match.group("ano_curto") or match.group("ano")
            ref = LegalReference(
                tipo=tipo,
                numero=match.group("numero").replace(".", ""),
                ano=int(ano) if ano else None,
            )
            if ref not in found:
                found.append(ref)
    return found


class BrLegislationConnector(BaseGovConnector):
    source_id = "br.legislacao"
    country = Country.BR
    publisher = "Legislação Federal - Senado Federal / Presidência da República"
    base_url = "https://legis.senado.leg.br/dadosabertos"
    domains = frozenset({Domain.LEGAL_JUSTICE, Domain.POLITICS_LEGISLATION})

    async def lookup(self, ref: LegalReference) -> list[dict[str, Any]]:
        payload = await self._get_json(
            "/legislacao/lista", {"tipo": ref.tipo, "numero": ref.numero, "ano": ref.ano}
        )
        lista = payload.get("ListaDocumento") if isinstance(payload, dict) else None
        docs = (lista or {}).get("documentos") or {}
        items = docs.get("documento", []) if isinstance(docs, dict) else []
        return [items] if isinstance(items, dict) else list(items)

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        refs = parse_legal_references([*query.legal_references, *query.keywords])
        evidence = []
        for ref in refs[:3]:
            for doc in (await self.lookup(ref))[:2]:
                evidence.append(
                    self._evidence(
                        title=doc.get("normaNome") or ref.label,
                        url=f"https://legis.senado.leg.br/norma/{doc.get('id')}",
                        excerpt=truncate(doc.get("ementa")),
                        venue="Diário Oficial da União",
                        published_at=parse_br_date(doc.get("dataassinatura")),
                        identifiers={"norma": doc.get("norma") or ref.label},
                        data={"apelido": doc.get("apelido"), "tipo": doc.get("descricao")},
                    )
                )
        return evidence


# =====================================================================================
# STJ - precedentes qualificados (open dataset)
# =====================================================================================
STJ_TEMAS_CSV_URL = (
    "https://dadosabertos.web.stj.jus.br/dataset/4238da2f-c07b-4c1a-b345-4402accacdcf/resource/"
    "df29da13-7d6b-41ba-ad96-cd1a5bbd191c/download/temas.csv"
)
STJ_TEMA_URL = (
    "https://processo.stj.jus.br/repetitivos/temas_repetitivos/pesquisa.jsp?novaConsulta=true"
    "&tipo_pesquisa=T&cod_tema_inicial={n}&cod_tema_final={n}"
)
STJ_PRECEDENTES_URL = "https://www.stj.jus.br/sites/portalp/Precedentes"
_SEARCH_FIELDS = (
    "questaoSubmetidaAJulgamento",
    "teseFirmada",
    "Assuntos",
    "referenciaLegislativa",
    "sumulaOriginada",
    "descricaoRepercussaoGeral",
)


class StjPrecedentsConnector(BaseGovConnector):
    """Searches the STJ qualified-precedents dataset locally (downloaded once, cached ~24h)."""

    source_id = "br.stj_precedentes"
    country = Country.BR
    publisher = "Superior Tribunal de Justiça (STJ) - Dados Abertos"
    base_url = "https://dadosabertos.web.stj.jus.br"
    domains = frozenset({Domain.LEGAL_JUSTICE})

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        dataset_timeout_seconds: float = 30.0,
        dataset_ttl_seconds: float = 86_400.0,
        **kw: Any,
    ) -> None:
        super().__init__(client, **kw)
        self.dataset_timeout_seconds = dataset_timeout_seconds
        self.dataset_ttl_seconds = dataset_ttl_seconds
        self._parsed: tuple[int, list[tuple[dict[str, str], str]]] | None = None

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> StjPrecedentsConnector:
        return cls(
            client,
            dataset_timeout_seconds=settings.dataset_timeout_seconds,
            dataset_ttl_seconds=settings.dataset_cache_ttl_seconds,
            **common,
        )

    async def warm_up(self) -> None:
        await self.temas()

    async def temas(self) -> list[tuple[dict[str, str], str]]:
        """Rows paired with their pre-normalized search text."""
        # The ~2.5 MB CSV regularly takes >8 s to download: it is a bulk dataset, so it gets
        # its own (configurable) timeout and a long cache instead of the 8 s query timeout.
        text = await self._request(
            STJ_TEMAS_CSV_URL,
            kind="text",
            request_timeout=self.dataset_timeout_seconds,
            cache_ttl=self.dataset_ttl_seconds,
        )
        if self._parsed is None or self._parsed[0] != id(text):
            rows = csv.DictReader(io.StringIO(text.lstrip("﻿")))
            indexed = [
                (row, normalize(" ".join(row.get(k) or "" for k in _SEARCH_FIELDS))) for row in rows
            ]
            self._parsed = (id(text), indexed)
        return self._parsed[1]

    async def search(self, terms: list[str], *, limit: int = 5) -> list[dict[str, str]]:
        needles = [normalize(t) for t in terms if t and len(t.strip()) > 2]
        if not needles:
            return []
        scored = []
        for row, haystack in await self.temas():
            matched = [n for n in needles if n in haystack]
            if not matched:
                continue
            score = 10 * len(matched) + sum(haystack.count(n) for n in matched)
            if (row.get("teseFirmada") or "").strip():
                score += 5
            if "cancelad" in normalize(row.get("situacao") or ""):
                score -= 8
            scored.append((score, row))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [row for _, row in scored[:limit]]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        evidence = []
        for row in await self.search([*query.keywords, *query.topics], limit=query.max_results):
            tipo = (row.get("tipoPrecedente") or "Precedente").strip()
            numero = (row.get("numeroPrecedente") or "").strip()
            tese = (row.get("teseFirmada") or "").strip()
            identifiers = {"precedente": f"{tipo} {numero}"}
            if (row.get("sumulaOriginada") or "").strip():
                identifiers["sumula_stj"] = row["sumulaOriginada"].strip()
            if (row.get("numeroRepercussaoGeralSTF") or "").strip():
                identifiers["tema_rg_stf"] = row["numeroRepercussaoGeralSTF"].strip()
            evidence.append(
                self._evidence(
                    title=f"STJ - {tipo} {numero}" + (" (tese firmada)" if tese else ""),
                    url=STJ_TEMA_URL.format(n=numero) if tipo == "Tema" else STJ_PRECEDENTES_URL,
                    excerpt=truncate(
                        f"Tese: {tese}" if tese else row.get("questaoSubmetidaAJulgamento"), 900
                    ),
                    venue="Superior Tribunal de Justiça",
                    published_at=parse_br_date(
                        row.get("dataPublicacaoAcordao") or row.get("dataJulgamento")
                    ),
                    identifiers=identifiers,
                    data={
                        "situacao": row.get("situacao"),
                        "orgao_julgador": row.get("orgaoJulgador"),
                        "assuntos": row.get("Assuntos"),
                        "referencia_legislativa": truncate(row.get("referenciaLegislativa"), 300),
                        "repercussao_geral_stf": truncate(
                            row.get("descricaoRepercussaoGeral"), 300
                        ),
                    },
                )
            )
        return evidence


# =====================================================================================
# EUR-Lex (Publications Office of the EU - Cellar SPARQL)
# =====================================================================================
EURLEX_URL = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:{celex}"
_SPARQL_SAFE = re.compile(r"[^\w\s]", re.UNICODE)
_CELEX_TYPES = {"R": "Regulamento", "L": "Diretiva", "D": "Decisão", "H": "Recomendação"}
_EU_LANGUAGE = "http://publications.europa.eu/resource/authority/language/{lang}"


def build_eurlex_query(terms: list[str], *, limit: int, language: str = "ENG") -> str:
    """SPARQL over Cellar using Virtuoso's full-text index (``bif:contains``).

    A plain ``FILTER(CONTAINS(...))`` scans every title and takes 20-30 s; the text index answers
    in ~0.1 s, inside the 8 s budget. ``terms`` must already be sanitized (letters, digits and
    spaces only), see ``EurLexConnector.search_acts``.
    """
    expression = " AND ".join(f'"{term}"' for term in terms)
    return (
        "PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>\n"
        "SELECT DISTINCT ?celex ?title ?date WHERE {\n"
        "  ?expr cdm:expression_title ?title .\n"
        f"  ?title bif:contains '{expression}' .\n"
        f"  ?expr cdm:expression_uses_language <{_EU_LANGUAGE.format(lang=language)}> ;\n"
        "        cdm:expression_belongs_to_work ?work .\n"
        "  ?work cdm:resource_legal_id_celex ?celex ;\n"
        "        cdm:work_date_document ?date .\n"
        '  FILTER(STRSTARTS(STR(?celex), "3"))\n'
        f"}} ORDER BY DESC(?date) LIMIT {int(limit)}"
    )


class EurLexConnector(BaseGovConnector):
    source_id = "eu.eurlex"
    country = Country.EU
    publisher = "EUR-Lex - Publications Office of the European Union"
    base_url = "https://publications.europa.eu/webapi/rdf/sparql"
    domains = frozenset({Domain.LEGAL_JUSTICE})

    async def search_acts(self, terms: list[str], *, limit: int = 5) -> list[dict[str, str]]:
        safe = [" ".join(_SPARQL_SAFE.sub(" ", t).lower().split()) for t in terms]
        # Virtuoso's text index rejects very short (noise) words.
        safe = [" ".join(w for w in t.split() if len(w) > 2) for t in safe]
        safe = [t for t in safe if t][:2]
        if not safe:
            return []
        acts = await self._query(safe, limit)
        if not acts and len(safe) > 1:
            acts = await self._query(safe[:1], limit)  # AND of two phrases was too strict
        return acts

    async def _query(self, terms: list[str], limit: int) -> list[dict[str, str]]:
        payload = await self._request(
            self.base_url,
            {"query": build_eurlex_query(terms, limit=limit)},
            headers={"Accept": "application/sparql-results+json"},
        )
        results = payload.get("results") if isinstance(payload, dict) else None
        bindings = (results or {}).get("bindings", [])
        return [{k: v.get("value", "") for k, v in row.items()} for row in bindings]

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        terms = query.keywords_en or query.keywords
        evidence = []
        for act in await self.search_acts(terms, limit=query.max_results):
            celex = act.get("celex", "")
            act_type = _CELEX_TYPES.get(celex[5:6], "Ato jurídico") if len(celex) > 5 else "Ato"
            evidence.append(
                self._evidence(
                    title=truncate(act.get("title"), 300),
                    url=EURLEX_URL.format(celex=celex),
                    excerpt=f"{act_type} da União Europeia (CELEX {celex}).",
                    venue="Official Journal of the European Union",
                    published_at=_iso(act.get("date")),
                    identifiers={"celex": celex},
                    data={"act_type": act_type},
                )
            )
        return evidence


def _iso(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


# =====================================================================================
# Judilibre - Cour de cassation (via PISTE)
# =====================================================================================
COUR_DE_CASSATION_URL = "https://www.courdecassation.fr/decision/{id}"


class CourDeCassationConnector(BaseGovConnector):
    source_id = "fr.judilibre"
    country = Country.FR
    publisher = "Cour de cassation - Judilibre"
    base_url = "https://api.piste.gouv.fr/cassation/judilibre/v1.0"
    domains = frozenset({Domain.LEGAL_JUSTICE})

    def __init__(
        self, client: httpx.AsyncClient | None = None, *, auth: PisteAuth | None = None, **kw: Any
    ) -> None:
        super().__init__(client, **kw)
        self._auth = auth

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        client: httpx.AsyncClient,
        extras: dict[str, Any] | None = None,
        **common: Any,
    ) -> CourDeCassationConnector:
        auth = (extras or {}).get("piste_auth") or PisteAuth(
            client,
            settings.piste_client_id,
            settings.piste_client_secret,
            sandbox=settings.piste_sandbox,
        )
        return cls(client, auth=auth, **common)

    @property
    def disabled_reason(self) -> str | None:
        if self._auth is None or not self._auth.configured:
            return "requires VERITAS_PISTE_CLIENT_ID / VERITAS_PISTE_CLIENT_SECRET"
        return None

    def _url(self, path: str) -> str:
        if self._auth is not None and self._auth.sandbox and not path.startswith("http"):
            return f"{self._auth.api_url}/cassation/judilibre/v1.0/{path.lstrip('/')}"
        return super()._url(path)

    async def _auth_headers(self) -> dict[str, str]:
        return await self._auth.headers() if self._auth else {}

    async def search_decisions(self, text: str, *, limit: int = 5) -> list[dict[str, Any]]:
        payload = await self._get_json("/search", {"query": text, "page_size": limit})
        return payload.get("results", []) if isinstance(payload, dict) else []

    async def search_evidence(self, query: EvidenceQuery) -> list[Evidence]:
        text = query.text
        if not text:
            return []
        evidence = []
        for decision in await self.search_decisions(text, limit=query.max_results):
            highlights = (decision.get("highlights") or {}).get("text") or []
            summary = decision.get("summary") or " ".join(highlights)
            number = decision.get("number") or ""
            title = " ".join(
                part
                for part in (
                    "Cour de cassation,",
                    decision.get("chamber") or "",
                    decision.get("decision_date") or "",
                    f"n° {number}" if number else "",
                )
                if part
            )
            evidence.append(
                self._evidence(
                    title=title,
                    url=COUR_DE_CASSATION_URL.format(id=decision.get("id", "")),
                    excerpt=truncate(re.sub(r"<[^>]+>", "", summary)),
                    venue="Cour de cassation",
                    published_at=_iso(decision.get("decision_date")),
                    identifiers={"pourvoi": number, "judilibre_id": str(decision.get("id", ""))},
                    data={"solution": decision.get("solution"), "themes": decision.get("themes")},
                )
            )
        return evidence
