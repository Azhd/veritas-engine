"""Legal connectors: BR federal legislation, STJ precedents, EUR-Lex, Judilibre (all mocked)."""

from __future__ import annotations

import csv
import io
from datetime import date

import httpx
import pytest
from pydantic import SecretStr

from app.connectors.legal_justice import (
    STJ_TEMAS_CSV_URL,
    BrLegislationConnector,
    CourDeCassationConnector,
    EurLexConnector,
    LegalReference,
    StjPrecedentsConnector,
    build_eurlex_query,
    parse_legal_references,
)
from app.connectors.piste import PisteAuth
from app.schemas.evidence import Country, EvidenceQuery
from tests.conftest import SleepRecorder, json_response, mock_client

# =============================================================== citation parsing


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("A Lei nº 12.965/2014 (Marco Civil)", [LegalReference("LEI", "12965", 2014)]),
        ("lei 8080, de 19 de setembro de 1990", [LegalReference("LEI", "8080", 1990)]),
        ("Lei Complementar 101/2000", [LegalReference("LCP", "101", 2000)]),
        ("o Decreto-Lei nº 2.848, de 1940", [LegalReference("DEL", "2848", 1940)]),
        ("Decreto 11.000/2022", [LegalReference("DEC", "11000", 2022)]),
        ("a Medida Provisória 1.154/2023", [LegalReference("MPV", "1154", 2023)]),
        ("Emenda Constitucional nº 132/2023", [LegalReference("EMC", "132", 2023)]),
        ("lei 14.133", [LegalReference("LEI", "14133", None)]),
        ("nenhuma norma aqui, só 2014", []),
    ],
)
def test_parse_legal_references(text, expected):
    assert parse_legal_references([text]) == expected


def test_parse_legal_references_deduplicates():
    refs = parse_legal_references(["Lei 12.965/2014", "lei nº 12965/2014"])
    assert refs == [LegalReference("LEI", "12965", 2014)]
    assert refs[0].label == "Lei 12965/2014"


# =============================================================== Senado / Planalto
SENADO_NORMA = {
    "ListaDocumento": {
        "documentos": {
            "documento": {  # single result comes as an object, not a list
                "id": "584776",
                "tipo": "LEI-n",
                "descricao": "Lei Numerada",
                "numero": "12965",
                "norma": "LEI-12965-2014-04-23",
                "normaNome": "Lei nº 12.965 de 23/04/2014",
                "ementa": "Estabelece princípios, garantias, direitos e deveres para o uso da "
                "Internet no Brasil.",
                "dataassinatura": "23/04/2014",
                "apelido": "Marco Civil da Internet (2014)",
            }
        }
    }
}


class TestBrLegislation:
    async def test_lookup_by_citation(self):
        seen = []

        def handler(request):
            seen.append(request.url)
            return json_response(SENADO_NORMA)

        conn = BrLegislationConnector(mock_client(handler), sleep=SleepRecorder())
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["marco civil"], legal_references=["Lei nº 12.965/2014"])
        )
        assert seen[0].path == "/dadosabertos/legislacao/lista"
        assert dict(seen[0].params) == {"tipo": "LEI", "numero": "12965", "ano": "2014"}
        item = evidence[0]
        assert item.title == "Lei nº 12.965 de 23/04/2014"
        assert item.url == "https://legis.senado.leg.br/norma/584776"
        assert item.published_at == date(2014, 4, 23)
        assert item.identifiers == {"norma": "LEI-12965-2014-04-23"}
        assert "uso da Internet" in item.excerpt
        assert item.venue == "Diário Oficial da União"

    async def test_empty_result_and_no_citation(self):
        conn = BrLegislationConnector(
            mock_client(lambda r: json_response({"ListaDocumento": {"documentos": ""}}))
        )
        assert await conn.search_evidence(EvidenceQuery(legal_references=["Lei 1/1900"])) == []
        assert await conn.search_evidence(EvidenceQuery(keywords=["sem lei citada"])) == []


# =============================================================== STJ precedents
STJ_FIELDS = [
    "sequencialPrecedente", "tipoPrecedente", "numeroPrecedente", "dataJulgamento",
    "dataPublicacaoAcordao", "situacao", "questaoSubmetidaAJulgamento", "teseFirmada",
    "referenciaLegislativa", "sumulaOriginada", "orgaoJulgador", "Assuntos",
    "numeroRepercussaoGeralSTF", "descricaoRepercussaoGeral",
]  # fmt: skip
STJ_ROWS = [
    {
        "tipoPrecedente": "Tema", "numeroPrecedente": "952", "situacao": "Trânsito em Julgado",
        "dataPublicacaoAcordao": "2016-12-19",
        "questaoSubmetidaAJulgamento": "Validade de reajuste de plano de saúde por faixa etária.",
        "teseFirmada": "O reajuste de mensalidade de plano de saúde por faixa etária é válido "
        "desde que previsto em contrato.",
        "Assuntos": "DIREITO DO CONSUMIDOR, Planos de Saúde", "sumulaOriginada": "Súmula 608",
        "numeroRepercussaoGeralSTF": "381", "orgaoJulgador": "S2",
    },
    {
        "tipoPrecedente": "Controvérsia", "numeroPrecedente": "1", "situacao": "Cancelada",
        "questaoSubmetidaAJulgamento": "Plano de saúde e faixa etária (controvérsia antiga).",
        "Assuntos": "Planos de Saúde",
    },
    {
        "tipoPrecedente": "Tema", "numeroPrecedente": "100", "situacao": "Afetado",
        "questaoSubmetidaAJulgamento": "Prescrição tributária.", "Assuntos": "DIREITO TRIBUTÁRIO",
    },
]  # fmt: skip


def _stj_csv() -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=STJ_FIELDS)
    writer.writeheader()
    for row in STJ_ROWS:
        writer.writerow({k: row.get(k, "") for k in STJ_FIELDS})
    return "﻿" + buffer.getvalue()


class TestStjPrecedents:
    async def test_search_ranks_theses_and_maps_identifiers(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, text=_stj_csv())

        conn = StjPrecedentsConnector(
            mock_client(handler), dataset_timeout_seconds=30, sleep=SleepRecorder()
        )
        evidence = await conn.search_evidence(
            EvidenceQuery(keywords=["plano de saúde", "faixa etária"])
        )
        assert str(seen[0].url) == STJ_TEMAS_CSV_URL
        assert seen[0].extensions["timeout"]["read"] == 30  # bulk dataset timeout
        assert [e.identifiers["precedente"] for e in evidence] == ["Tema 952", "Controvérsia 1"]
        top = evidence[0]
        assert top.title == "STJ - Tema 952 (tese firmada)"
        assert top.excerpt.startswith("Tese: O reajuste de mensalidade")
        assert top.identifiers["sumula_stj"] == "Súmula 608"
        assert top.identifiers["tema_rg_stf"] == "381"
        assert "cod_tema_inicial=952" in top.url
        assert top.published_at == date(2016, 12, 19)
        assert top.country is Country.BR
        # Non-"Tema" precedents point to the generic precedents page.
        assert evidence[1].url.startswith("https://www.stj.jus.br/")

    async def test_dataset_downloaded_once_and_cached(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, text=_stj_csv())

        conn = StjPrecedentsConnector(mock_client(handler))
        await conn.warm_up()
        await conn.search(["tributária"])
        await conn.search(["faixa etária"])
        assert calls["n"] == 1

    async def test_no_matches(self):
        conn = StjPrecedentsConnector(mock_client(lambda r: httpx.Response(200, text=_stj_csv())))
        assert await conn.search_evidence(EvidenceQuery(keywords=["astronomia"])) == []


# =============================================================== EUR-Lex
SPARQL_RESULT = {
    "head": {"vars": ["celex", "title", "date"]},
    "results": {
        "bindings": [
            {
                "celex": {"value": "32024R1689"},
                "title": {"value": "Regulation (EU) 2024/1689 laying down harmonised rules on "
                          "artificial intelligence (Artificial Intelligence Act)"},
                "date": {"value": "2024-06-13"},
            }
        ]
    },
}  # fmt: skip


class TestEurLex:
    async def test_sparql_query_and_mapping(self):
        seen = []

        def handler(request):
            seen.append(request)
            return json_response(SPARQL_RESULT)

        conn = EurLexConnector(mock_client(handler), sleep=SleepRecorder())
        evidence = await conn.search_evidence(
            EvidenceQuery(
                keywords=["inteligência artificial"], keywords_en=["Artificial Intelligence"]
            )
        )
        request = seen[0]
        assert request.headers["Accept"] == "application/sparql-results+json"
        query = request.url.params["query"]
        assert "?title bif:contains '\"artificial intelligence\"'" in query
        assert "ORDER BY DESC(?date)" in query
        item = evidence[0]
        assert item.country is Country.EU
        assert item.url == "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689"
        assert item.identifiers == {"celex": "32024R1689"}
        assert item.data["act_type"] == "Regulamento"
        assert item.published_at == date(2024, 6, 13)

    async def test_sparql_injection_is_neutralized(self):
        seen = []

        def handler(request):
            seen.append(request.url.params["query"])
            return json_response({"results": {"bindings": []}})

        conn = EurLexConnector(mock_client(handler))
        await conn.search_acts(['ai")) } DROP ALL #', "x"])
        query = seen[0]
        # Quotes, braces and noise words are stripped before reaching the text index.
        assert "?title bif:contains '\"drop all\"'" in query
        assert query.count("'") == 2 and query.count('"') == 4
        assert len(seen) == 1

    async def test_two_terms_fall_back_to_first_when_empty(self):
        seen = []

        def handler(request):
            query = request.url.params["query"]
            seen.append(query)
            if " AND " in query:
                return json_response({"results": {"bindings": []}})
            return json_response(SPARQL_RESULT)

        conn = EurLexConnector(mock_client(handler))
        acts = await conn.search_acts(["artificial intelligence", "liability"])
        assert '\'"artificial intelligence" AND "liability"\'' in seen[0]
        assert "AND" not in seen[1].split("bif:contains")[1].split("\n")[0]
        assert acts[0]["celex"] == "32024R1689"

    def test_build_query_limit(self):
        assert build_eurlex_query(["x y"], limit=3).rstrip().endswith("LIMIT 3")


# =============================================================== Judilibre (PISTE)
class TestJudilibre:
    async def test_disabled_without_credentials(self):
        client = mock_client(lambda r: httpx.Response(500))
        conn = CourDeCassationConnector(client, auth=PisteAuth(client, None, None))
        assert not conn.enabled and "PISTE" in conn.disabled_reason

    async def test_search_with_oauth_token(self):
        token_calls = {"n": 0}
        api_requests = []

        def handler(request):
            if request.url.host == "oauth.piste.gouv.fr":
                token_calls["n"] += 1
                assert b"grant_type=client_credentials" in request.content
                return json_response({"access_token": "tok-1", "expires_in": 3600})
            api_requests.append(request)
            return json_response(
                {
                    "results": [
                        {
                            "id": "64f1a2b3c4",
                            "chamber": "soc",
                            "number": "21-12.345",
                            "decision_date": "2023-05-10",
                            "solution": "cassation",
                            "highlights": {"text": ["Le <em>licenciement</em> est nul..."]},
                        }
                    ]
                }
            )

        client = mock_client(handler)
        conn = CourDeCassationConnector(
            client, auth=PisteAuth(client, SecretStr("id"), SecretStr("secret"))
        )
        assert conn.enabled
        evidence = await conn.search_evidence(EvidenceQuery(keywords=["licenciement nul"]))
        await conn.search_evidence(EvidenceQuery(keywords=["autre recherche"]))
        assert token_calls["n"] == 1  # token reused
        assert api_requests[0].headers["Authorization"] == "Bearer tok-1"
        assert api_requests[0].url.path == "/cassation/judilibre/v1.0/search"
        item = evidence[0]
        assert item.url == "https://www.courdecassation.fr/decision/64f1a2b3c4"
        assert item.excerpt == "Le licenciement est nul..."
        assert item.identifiers["pourvoi"] == "21-12.345"
        assert item.published_at == date(2023, 5, 10)
        assert item.title == "Cour de cassation, soc 2023-05-10 n° 21-12.345"
