"""
column_mapper.py — Generisk, återanvändbar kolumnmappning för att hantera att
Svea (och andra externa källor) inte garanterat använder exakt samma
kolumnnamn i varje export/API-svar.

Detta är en Python-portering av samma HINTS + bestMatch()-logik som redan
finns i frontend (ren JS). Genom att använda IDENTISK matchningslogik på
båda ställena beter sig manuell Excel-import (frontend) och automatisk
daglig import (backend) exakt likadant.

Matchningsordning (samma som frontend):
    1. Exakt matchning (efter normalisering: gemener, mellanslag/understreck bort)
    2. Kolumnnamnet INNEHÅLLER ledtråden (t.ex. "Fakturanr (Svea)" innehåller "fakturanr")
    3. Ledtråden INNEHÅLLER kolumnnamnet (omvänd matchning, för korta/förkortade namn)
"""

from typing import Optional


# Samma synonymer som HINTS-objektet i frontend. Om ni lägger till fler
# synonymer i JS, spegla ändringen här också så att de två håller sig i synk.
HINTS: dict[str, list[str]] = {
    "orderSvea": ["fakturanr", "ordernr", "ordernummer", "order", "faktura", "invoice", "id"],
    "orderHemfint": ["hemfint", "hf", "intern"],
    "kund": ["kundnamn", "kund", "namn", "customer", "företag"],
    "belopp": ["restbel", "belopp", "summa", "amount", "saldo"],
    "fakturadatum": ["fakturadatum", "faktdatum", "datum"],
    "forfallodatum": ["förfdat", "forfdat", "förfallodatum", "förfall"],
}


def _normalize(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace("_", "").replace("-", "")


def best_match(target_field: str, available_columns: list[str]) -> Optional[str]:
    """
    Hittar det kolumnnamn i `available_columns` som bäst matchar `target_field`
    (t.ex. "orderSvea", "kund", "belopp"...).

    Returnerar det ORIGINALA kolumnnamnet (så det går att slå upp i raddatan),
    eller None om ingen rimlig matchning hittades.
    """
    hints = HINTS.get(target_field, [])
    if not hints:
        return None

    normalized_cols = {_normalize(c): c for c in available_columns}

    # 1. Exakt matchning
    for hint in hints:
        if hint in normalized_cols:
            return normalized_cols[hint]

    # 2. Kolumn innehåller ledtråd
    for hint in hints:
        for norm_col, original_col in normalized_cols.items():
            if hint in norm_col:
                return original_col

    # 3. Ledtråd innehåller kolumn (omvänd matchning)
    for hint in hints:
        for norm_col, original_col in normalized_cols.items():
            if norm_col and norm_col in hint:
                return original_col

    return None


def map_columns(available_columns: list[str]) -> dict[str, Optional[str]]:
    """
    Kör best_match() för samtliga kända fält samtidigt.

    Exempel:
        >>> map_columns(["Fakturanr", "Kundnamn", "Restbel", "Förfdat"])
        {
            "orderSvea": "Fakturanr",
            "orderHemfint": None,
            "kund": "Kundnamn",
            "belopp": "Restbel",
            "fakturadatum": None,
            "forfallodatum": "Förfdat",
        }
    """
    return {field: best_match(field, available_columns) for field in HINTS}
