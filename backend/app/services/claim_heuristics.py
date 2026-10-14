"""Deterministic claim analysis: zero-cost, no LLM required.

Used by the citizen mode (no AI key) and as a safety net when the LLM triage fails. It also
extracts URLs and legal citations deterministically even when an LLM is available, so those
never depend on the model.
"""

from __future__ import annotations

import re
import unicodedata

from app.connectors.legal_justice import parse_legal_references
from app.schemas.evidence import Domain
from app.schemas.fact_check import ClaimAnalysis, CountryContext


def normalize(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c))


# ---------------------------------------------------------------------- country
_BR_MARKERS = (
    "brasil", "brasileir", "camara dos deputados", "senado federal", "stf", "stj", "ibge", "sus",
    "lula", "bolsonaro", "planalto", "reais", "r$", "sao paulo", "rio de janeiro",
    "congresso nacional", "governo federal", "deputado", "deputada", "ministerio", "anvisa",
)  # fmt: skip
_FR_MARKERS = (
    "france", "francais", "francaise", "assemblee nationale", "senat", "insee", "macron",
    "elysee", "matignon", "paris", "gouvernement", "depute", "ministere", "loi ",
)  # fmt: skip
_PT_WORDS = {
    "nao", "que", "de", "do", "da", "os", "as", "um", "uma", "para", "com", "foi", "sao", "por",
    "no", "na", "nos", "em", "ao",
}  # fmt: skip
_FR_WORDS = {"le", "la", "les", "des", "est", "une", "pour", "avec", "pas", "ont", "sont", "du"}
_STOPWORDS = _PT_WORDS | _FR_WORDS | {
    "e", "o", "a", "em", "no", "na", "nos", "por", "mais", "menos", "sobre", "ao", "aos", "seu",
    "sua", "et", "en", "au", "aux", "dans", "sur", "par", "qui", "ce", "cette", "il", "elle",
    "ser", "ter", "tem", "teve", "ja", "isso", "este", "esta", "entre", "desde", "ano", "anos",
    "causa", "causam", "provoca", "todos", "todas", "muito", "pode", "podem", "vai", "fazer",
    "cause", "tous", "fait", "peut", "plus", "selon", "segundo", "disse", "afirma", "http",
    "https", "www", "verdade", "mentira", "vrai", "faux", "depuis", "double", "dobrou",
}  # fmt: skip


def heuristic_country(claim: str) -> CountryContext:
    text = normalize(claim)
    br = sum(marker in text for marker in _BR_MARKERS)
    fr = sum(marker in text for marker in _FR_MARKERS)
    if parse_legal_references([claim]):
        br += 1  # citations like "Lei 12.965/2014" follow the Brazilian federal format
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


# ---------------------------------------------------------------------- keywords
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)


def extract_urls(claim: str) -> list[str]:
    return list(dict.fromkeys(m.rstrip(".,;:!?)]}") for m in _URL_RE.findall(claim)))


def heuristic_keywords(claim: str, limit: int = 5) -> list[str]:
    text = _URL_RE.sub(" ", claim)
    words = re.findall(r"[\wÀ-ÿ]+", text.lower())
    seen: list[str] = []
    for word in words:
        if len(word) < 4 or word.isdigit() or normalize(word) in _STOPWORDS:
            continue
        if word not in seen:
            seen.append(word)
    return sorted(seen, key=len, reverse=True)[:limit]


# ---------------------------------------------------------------------- domains
_DOMAIN_TRIGGERS: dict[Domain, tuple[str, ...]] = {
    Domain.HEALTH_SCIENCE: (
        "vacin", "vaccin", "covid", "virus", "doenca", "maladie", "saude", "sante", "cancer",
        "remedio", "medicament", "tratamento", "traitement", "cura ", "autism", "ivermectin",
        "cloroquin", "chloroquin", "cientific", "scientifi", "epidemi", "pandemi", "gripe",
        "grippe", "dengue", "sarampo", "rougeole", "hiv", "aids", "obesi", "diabet",
        "expectativa de vida", "esperance de vie", "mortalidade", "mortalite", "oms", "anvisa",
        "estudo", "etude", "medic", "hospital", "tabac", "tabaco", "malaria", "tuberculos",
    ),
    Domain.GEOPOLITICS: (
        "guerra", "guerre", "conflito", "conflit", "cessar-fogo", "cessez-le-feu", "onu ",
        "otan", "nato", "invas", "refugiad", "refugie", "humanitari", "ucrania", "ukraine",
        "russia", "russie", "israel", "gaza", "palestin", "ira ", "iran", "sudao", "soudan",
        "bombarde", "sancoes", "sanctions", "tratado", "traite", "genocid", "militar",
    ),
    Domain.LEGAL_JUSTICE: (
        "lei ", "loi ", "decreto", "decret", "stf", "stj", "supremo", "tribunal", "sumula",
        "jurisprud", "constitui", "inconstitucional", "codigo penal", "code penal", "crime",
        "cour de cassation", "juiz", "juge", "julgament", "direito", "droit", "diretiva",
        "directive", "uniao europeia", "union europeenne", "regulamento", "reglement", "ilegal",
        "illegal", "proibid", "interdit", "medida provisoria",
    ),
    Domain.ECONOMY_STATISTICS: (
        "inflac", "inflation", "ipca", "desempreg", "desocupa", "chomage", "pib", "populac",
        "population", "habitantes", "salario", "salaire", "imposto", "impot", "orcamento",
        "budget", "divida", "dette", "pobreza", "pauvrete", "renda", "revenu", "economia",
        "economie", "precos", "prix",
    ),
    Domain.POLITICS_LEGISLATION: (
        "deputad", "senador", "senat", "projeto de lei", "votac", "vote", "congresso",
        "camara", "assemblee", "depute", "presidente", "president", "ministr", "governo",
        "gouvernement", "eleic", "election", "partido", "parti ", "emenda",
    ),
}  # fmt: skip


def heuristic_domains(claim: str, urls: list[str] | None = None) -> list[Domain]:
    text = f" {normalize(claim)} "
    domains = [d for d, triggers in _DOMAIN_TRIGGERS.items() if any(t in text for t in triggers)]
    if urls:
        domains.append(Domain.WEB_HISTORY)
    return domains


# ---------------------------------------------------------------------- PT/FR -> EN glossary
#: Small offline glossary so international sources (PubMed, WHO, GDELT, EUR-Lex) remain usable
#: without an LLM. Keys are normalized (lowercase, no accents); longer phrases win.
GLOSSARY_EN: dict[str, str] = {
    "expectativa de vida": "life expectancy", "esperance de vie": "life expectancy",
    "mortalidade infantil": "infant mortality", "mortalite infantile": "infant mortality",
    "inteligencia artificial": "artificial intelligence",
    "intelligence artificielle": "artificial intelligence",
    "protecao de dados": "data protection", "protection des donnees": "data protection",
    "mudancas climaticas": "climate change", "mudanca climatica": "climate change",
    "changement climatique": "climate change", "cessar-fogo": "ceasefire",
    "cessez-le-feu": "ceasefire", "hidroxicloroquina": "hydroxychloroquine",
    "hydroxychloroquine": "hydroxychloroquine", "cloroquina": "chloroquine",
    "ivermectina": "ivermectin", "ivermectine": "ivermectin", "vacinas": "vaccines",
    "vacina": "vaccine", "vaccins": "vaccines", "vaccin": "vaccine", "autismo": "autism",
    "autisme": "autism", "covid": "covid-19", "cancer": "cancer", "sarampo": "measles",
    "rougeole": "measles", "dengue": "dengue", "gripe": "influenza", "grippe": "influenza",
    "diabetes": "diabetes", "diabete": "diabetes", "obesidade": "obesity", "obesite": "obesity",
    "tuberculose": "tuberculosis", "malaria": "malaria", "paludisme": "malaria", "hiv": "hiv",
    "tabaco": "tobacco", "tabac": "tobacco", "alcool": "alcohol", "aborto": "abortion",
    "avortement": "abortion", "mascara": "face mask", "masque": "face mask",
    "guerra": "war", "guerre": "war", "refugiados": "refugees", "refugies": "refugees",
    "ucrania": "ukraine", "russia": "russia", "russie": "russia", "gaza": "gaza",
    "israel": "israel", "sudao": "sudan", "soudan": "sudan", "fome": "hunger", "faim": "hunger",
    "desmatamento": "deforestation", "deforestation": "deforestation",
    "genocidio": "genocide", "genocide": "genocide", "sancoes": "sanctions",
}  # fmt: skip


def translate_terms(claim: str, limit: int = 4) -> list[str]:
    text = f" {normalize(claim)} "
    found: list[str] = []
    for source in sorted(GLOSSARY_EN, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(source)}(?![\w-])", text):
            english = GLOSSARY_EN[source]
            if english not in found:
                found.append(english)
            text = text.replace(source, " ")
    return found[:limit]


# ---------------------------------------------------------------------- full analysis
def heuristic_analysis(claim: str) -> ClaimAnalysis:
    country = heuristic_country(claim)
    urls = extract_urls(claim)
    english = translate_terms(claim)
    keywords = heuristic_keywords(claim)
    return ClaimAnalysis(
        country=country,
        keywords=keywords,
        keywords_en=english,
        topics=keywords,
        topics_en=english,
        domains=heuristic_domains(claim, urls),
        legal_references=[ref.label for ref in parse_legal_references([claim])],
        urls=urls,
        language="fr" if country is CountryContext.FR else "pt",
    )


def enrich_analysis(analysis: ClaimAnalysis, claim: str) -> ClaimAnalysis:
    """Merge deterministic extractions into an (LLM-produced) analysis."""
    urls = list(dict.fromkeys([*analysis.urls, *extract_urls(claim)]))
    refs = [ref.label for ref in parse_legal_references([claim])]
    domains = list(analysis.domains) or heuristic_domains(claim)
    if urls and Domain.WEB_HISTORY not in domains:
        domains.append(Domain.WEB_HISTORY)
    return analysis.model_copy(
        update={
            "keywords": analysis.keywords or heuristic_keywords(claim),
            "keywords_en": analysis.keywords_en or translate_terms(claim),
            "topics_en": analysis.topics_en or translate_terms(claim),
            "urls": urls[:5],
            "legal_references": list(dict.fromkeys([*analysis.legal_references, *refs]))[:5],
            "domains": domains,
        }
    )
