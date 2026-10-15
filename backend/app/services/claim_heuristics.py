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
_FR_WORDS = {
    "le", "la", "les", "des", "est", "une", "pour", "avec", "pas", "ont", "sont", "du", "et",
    "au", "aux", "dans", "sur", "qui", "cette", "depuis", "ete",
}  # fmt: skip
_EN_WORDS = {
    "the", "is", "are", "was", "were", "and", "of", "to", "that", "have", "has", "with", "for",
    "not", "this", "from", "they", "will", "been", "their", "does", "than", "it", "its", "in",
    "by", "be",
}  # fmt: skip
_EN_STOPWORDS = {
    "that", "have", "with", "this", "from", "they", "will", "were", "been", "their", "about",
    "into", "than", "said", "says", "claims", "claim", "shows", "show", "people", "years",
    "year", "after", "before", "last", "more", "over", "only", "because", "causes", "every",
    "what", "when", "which", "there", "these", "those", "would", "could", "should", "does",
    "made", "make", "just", "also", "very", "really", "many", "much", "most", "some", "news",
    "photo", "image", "share", "shared", "true", "false", "fake", "breaking", "today", "week",
    "month", "months", "since", "according", "everyone",
}  # fmt: skip
_STOPWORDS = _PT_WORDS | _FR_WORDS | _EN_STOPWORDS | {
    "e", "o", "a", "em", "no", "na", "nos", "por", "mais", "menos", "sobre", "ao", "aos", "seu",
    "sua", "et", "en", "au", "aux", "dans", "sur", "par", "qui", "ce", "cette", "il", "elle",
    "ser", "ter", "tem", "teve", "ja", "isso", "este", "esta", "entre", "desde", "ano", "anos",
    "causa", "causam", "provoca", "todos", "todas", "muito", "pode", "podem", "vai", "fazer",
    "cause", "tous", "fait", "peut", "plus", "selon", "segundo", "disse", "afirma", "http",
    "https", "www", "verdade", "mentira", "vrai", "faux", "depuis", "double", "dobrou",
    "video", "videos", "foto", "fotos", "imagem", "imagens", "redes", "sociais", "social",
    "afirmam", "afirmou", "dizem", "diz", "mostrando", "mostra", "mostram", "recente",
    "recentes", "massa", "inteira", "inteiro", "mensagem", "noticia", "post", "posts",
    "compartilhe", "compartilhar", "urgente", "atencao", "alerta", "circula", "circulam",
    "viral", "whatsapp", "facebook", "instagram", "tiktok", "youtube", "twitter", "pessoas",
    "gente", "agora", "hoje", "ontem", "semana", "segunda", "terca", "quarta", "quinta",
    "sexta", "sabado", "domingo", "feira", "partir", "vao", "sera", "serao", "ainda",
    "photos", "images", "reseaux", "sociaux", "montrent", "affirment",
    "confirmando", "confirma", "confirmou", "divulgou", "divulga", "relatorio",
    "relatorios", "ultimos", "ultimas", "observatorio", "consecutivos",
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
        "health", "disease", "cure ", "study", "studies", "measles", "flu ", "smoking",
    ),
    Domain.GEOPOLITICS: (
        "guerra", "guerre", "conflito", "conflit", "cessar-fogo", "cessez-le-feu", "onu ",
        "otan", "nato", "invas", "refugiad", "refugie", "humanitari", "ucrania", "ukraine",
        "russia", "russie", "israel", "gaza", "palestin", "ira ", "iran", "sudao", "soudan",
        "bombarde", "sancoes", "sanctions", "tratado", "traite", "genocid", "militar",
        " war ", "ceasefire", "conflict", "refugee", "treaty", "missile", "troops",
    ),
    Domain.LEGAL_JUSTICE: (
        "lei ", "loi ", "decreto", "decret", "stf", "stj", "supremo", "tribunal", "sumula",
        "jurisprud", "constitui", "inconstitucional", "codigo penal", "code penal", "crime",
        "cour de cassation", "juiz", "juge", "julgament", "direito", "droit", "diretiva",
        "directive", "regulamento europeu", "reglement europeen", "ilegal",
        "illegal", "proibid", "interdit", "medida provisoria",
        " law ", " laws ", "court", "constitution", "statute", "judge", "banned", "ruling",
    ),
    Domain.ECONOMY_STATISTICS: (
        "inflac", "inflation", "ipca", "desempreg", "desocupa", "chomage", "pib", "populac",
        "population", "habitantes", "salario", "salaire", "imposto", "impot", "orcamento",
        "budget", "divida", "dette", "pobreza", "pauvrete", "renda", "revenu", "economia",
        "economie", "precos", "prix",
        "unemployment", "gdp", " tax", "wage", "salary", "poverty", "debt", "price",
    ),
    Domain.CLIMATE_ENVIRONMENT: (
        "clima", "climat", "aquecimento", "rechauffement", "temperatura", "temperature",
        "onda de calor", "canicule", "efeito estufa", "effet de serre", "co2", "carbono",
        "carbone", "copernicus", "el nino", "degelo", "geleira", "glacier", "nivel do mar",
        "niveau de la mer", "desmatamento", "deforestation", "emissoes", "emissions",
        "acordo de paris", "accord de paris", "ipcc", "giec", "seca", "secheresse",
        "warming", "heatwave", "heat wave", "drought", "sea level", "carbon", "greenhouse",
        "wildfire", "plus chaud", "chaleur", "planete", "mais quente", "calor", "hottest",
        "warmest",
    ),
    Domain.POLITICS_LEGISLATION: (
        "deputad", "senador", "senat", "projeto de lei", "votac", "vote", "congresso",
        "camara", "assemblee", "depute", "presidente", "president", "ministr", "governo",
        "gouvernement", "eleic", "election", "partido", "parti ", "emenda",
        "congress", "parliament", "government", " bill ", "lawmaker",
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
    "ajuda humanitaria": "humanitarian aid", "aide humanitaire": "humanitarian aid",
    "comboio humanitario": "humanitarian convoy", "comboio": "convoy", "convoi": "convoy",
    "humanitario": "humanitarian", "humanitaire": "humanitarian", "militar": "military",
    "militaire": "military", "exercito": "army", "armee": "army", "ataque": "attack",
    "attaque": "attack", "bombardeio": "bombing", "bombardement": "bombing",
    "missil": "missile", "missile": "missile", "drone": "drone", "explosao": "explosion",
    "explosion": "explosion", "destruida": "destroyed", "destruido": "destroyed",
    "detruite": "destroyed", "escombros": "rubble", "decombres": "rubble",
    "terremoto": "earthquake", "seisme": "earthquake", "enchente": "flood",
    "inondation": "flood", "incendio": "wildfire", "furacao": "hurricane",
    "paracetamol": "acetaminophen", "grossesse": "pregnancy", "gravidez": "pregnancy",
    "refem": "hostage", "refens": "hostages", "otage": "hostage", "mortos": "killed",
    "vitimas": "casualties", "victimes": "casualties", "hospital": "hospital",
    "venezuela": "venezuela", "china": "china", "chine": "china", "ira": "iran",
    "libano": "lebanon", "liban": "lebanon", "siria": "syria", "syrie": "syria",
    "iemen": "yemen", "yemen": "yemen", "haiti": "haiti", "taiwan": "taiwan",
    "coreia do norte": "north korea", "coree du nord": "north korea",
    "estados unidos": "united states", "etats-unis": "united states",
    "aquecimento global": "global warming", "rechauffement climatique": "global warming",
    "temperatura media global": "global mean temperature", "temperatura": "temperature",
    "temperature": "temperature", "onda de calor": "heatwave", "canicule": "heatwave",
    "recordes": "record", "recorde": "record", "record": "record", "efeito estufa":
    "greenhouse effect", "nivel do mar": "sea level", "geleiras": "glaciers",
    "emissoes": "emissions", "seca": "drought", "secheresse": "drought",
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


# ---------------------------------------------------------------------- vagueness
_SPECIFIC_RE = re.compile(r"\d")


def is_vague(claim: str, domains: list[Domain] | None = None) -> bool:
    """True when an *event* claim names no place, person, date, number, link or law.

    Such claims ("a city was destroyed in a recent attack") cannot be cross-checked by any
    source; the user is asked for specifics instead of receiving an empty search. General
    claims ("vaccines cause autism") are checkable as they are and never flagged.
    """
    domains = heuristic_domains(claim) if domains is None else domains
    if Domain.GEOPOLITICS not in domains:
        return False
    text = _URL_RE.sub(" ", claim)
    if extract_urls(claim) or parse_legal_references([claim]) or _SPECIFIC_RE.search(text):
        return False
    words = re.findall(r"[\wÀ-ÿ-]+", text)
    proper = [
        w
        for i, w in enumerate(words)
        if i > 0 and w[:1].isupper() and normalize(w) not in _STOPWORDS and len(w) > 2
    ]
    if proper:
        return False
    normalized = f" {normalize(claim)} "
    return not any(marker in normalized for marker in (*_BR_MARKERS, *_FR_MARKERS))


VAGUE_CLAIM_TIP = (
    "A afirmação não diz onde, quando nem quem: assim nenhuma fonte consegue confirmar ou "
    "desmentir. Acrescente o nome da cidade ou do país, a data aproximada ou quem está "
    "envolvido e verifique de novo."
)


# ---------------------------------------------------------------------- full analysis
def heuristic_language(claim: str, hint: str | None = None) -> str:
    """'en', 'fr' or 'pt' by counting common function words; ``hint`` breaks ties."""
    words = re.findall(r"[a-z]+", normalize(claim))
    hits = {
        "pt": sum(w in _PT_WORDS for w in words),
        "fr": sum(w in _FR_WORDS for w in words),
        "en": sum(w in _EN_WORDS for w in words),
    }
    best = max(hits, key=lambda lang: hits[lang])
    if hits[best] == 0 or list(hits.values()).count(hits[best]) > 1:
        return hint if hint in hits else "pt"
    return best


def heuristic_analysis(claim: str, language_hint: str | None = None) -> ClaimAnalysis:
    country = heuristic_country(claim)
    urls = extract_urls(claim)
    english = translate_terms(claim)
    keywords = heuristic_keywords(claim)
    language = heuristic_language(claim, language_hint)
    if language == "en":
        # The claim is already in English: its own words query the international sources.
        english = list(dict.fromkeys([*keywords, *english]))[:8]
    elif country is CountryContext.FR:
        language = "fr"
    return ClaimAnalysis(
        country=country,
        keywords=keywords,
        keywords_en=english,
        topics=keywords,
        topics_en=english,
        domains=heuristic_domains(claim, urls),
        legal_references=[ref.label for ref in parse_legal_references([claim])],
        urls=urls,
        language=language,
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
