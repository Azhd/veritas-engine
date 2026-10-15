"""Country names in Portuguese, English and French -> ISO 3166-1 alpha-2 and Wikidata ids.

Shared by the international sources (World Bank, Eurostat, Wikidata). Names are matched as
whole normalized words, so "Franca" (the country, typed without the cedilla) is found but
Portuguese verbs that look like codes ("usa", "irá") are never countries.
"""

from __future__ import annotations

from app.connectors.br_gov import normalize

#: ISO2 -> (Wikidata id, names in PT/EN/FR, normalized: lower case, no accents).
COUNTRY_TABLE: dict[str, tuple[str, tuple[str, ...]]] = {
    "BR": ("Q155", ("brasil", "brazil", "bresil")),
    "FR": ("Q142", ("franca", "france")),
    "UA": ("Q212", ("ucrania", "ukraine")),
    "RU": ("Q159", ("russia", "russie")),
    "US": ("Q30", ("estados unidos", "eua", "united states", "etats-unis", "etats unis")),
    "DE": ("Q183", ("alemanha", "germany", "allemagne")),
    "GB": ("Q145", ("reino unido", "united kingdom", "royaume-uni", "inglaterra")),
    "PT": ("Q45", ("portugal",)),
    "ES": ("Q29", ("espanha", "spain", "espagne")),
    "IT": ("Q38", ("italia", "italy", "italie")),
    "CN": ("Q148", ("china", "chine")),
    "JP": ("Q17", ("japao", "japan", "japon")),
    "IN": ("Q668", ("india", "inde")),
    "IL": ("Q801", ("israel",)),
    "IR": ("Q794", ("iran",)),
    "AR": ("Q414", ("argentina", "argentine")),
    "MX": ("Q96", ("mexico", "mexique")),
    "CA": ("Q16", ("canada",)),
    "VE": ("Q717", ("venezuela",)),
    "CO": ("Q739", ("colombia", "colombie")),
    "CL": ("Q298", ("chile", "chili")),
    "PE": ("Q419", ("peru", "perou")),
    "BE": ("Q31", ("belgica", "belgium", "belgique")),
    "CH": ("Q39", ("suica", "switzerland", "suisse")),
    "PL": ("Q36", ("polonia", "poland", "pologne")),
    "TR": ("Q43", ("turquia", "turkey", "turquie")),
    "NL": ("Q55", ("holanda", "paises baixos", "netherlands", "pays-bas")),
    "SE": ("Q34", ("suecia", "sweden", "suede")),
    "GR": ("Q41", ("grecia", "greece", "grece")),
    "IE": ("Q27", ("irlanda", "ireland", "irlande")),
    "AT": ("Q40", ("austria", "autriche")),
    "AO": ("Q916", ("angola",)),
    "MZ": ("Q1029", ("mocambique", "mozambique")),
    "DZ": ("Q262", ("argelia", "algeria", "algerie")),
    "MA": ("Q1028", ("marrocos", "morocco", "maroc")),
    "SN": ("Q1041", ("senegal",)),
    "ZA": ("Q258", ("africa do sul", "south africa", "afrique du sud")),
    "KR": ("Q884", ("coreia do sul", "south korea", "coree du sud")),
    "KP": ("Q423", ("coreia do norte", "north korea", "coree du nord")),
    "PS": ("Q219060", ("palestina", "palestine")),
    "EG": ("Q79", ("egito", "egypt", "egypte")),
    "SA": ("Q851", ("arabia saudita", "saudi arabia", "arabie saoudite")),
}  # fmt: skip

#: European Union members (ISO2) - Eurostat publishes data for them and the EU as a whole.
EU_MEMBERS = frozenset({
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT",
    "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
})  # fmt: skip
#: Words that name the European Union itself.
EU_NAMES = ("uniao europeia", "european union", "union europeenne", "zona do euro", "eurozone",
            "zone euro")  # fmt: skip

_NAME_TO_ISO = {name: iso for iso, (_, names) in COUNTRY_TABLE.items() for name in names}


def countries_in(text: str) -> list[str]:
    """ISO2 codes of the countries named in ``text``, in table order, at most three."""
    padded = f" {normalize(text)} "
    found = [iso for name, iso in _NAME_TO_ISO.items() if f" {name} " in padded]
    return list(dict.fromkeys(found))[:3]


def country_names_in(text: str) -> set[str]:
    padded = f" {normalize(text)} "
    return {name for name in _NAME_TO_ISO if f" {name} " in padded}


def mentions_eu(text: str) -> bool:
    padded = f" {normalize(text)} "
    return any(f" {name} " in padded for name in EU_NAMES)


def wikidata_id(iso: str) -> str:
    return COUNTRY_TABLE[iso][0]
