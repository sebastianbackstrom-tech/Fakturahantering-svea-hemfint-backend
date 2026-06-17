"""
external_source.py — Hämtar data från din externa källa/API en gång om dagen.

Detta är en STUB. Fyll i fetch_external_data() med riktig logik när du vet
exakt vilket API/källa det rör sig om. Funktionen ska returnera en lista av
dictar med samma fältnamn som databasen använder, så att den går rakt in i
db.bulk_upsert_from_external().

Returformat (lista av dicts):
    [
        {
            "orderSvea": "1038296",
            "orderHemfint": "",
            "kund": "NÄSLUND, HANS GUNNAR",
            "belopp": "17168",
            "status": "open",
            "fakturadatum": "2025-11-02",
            "forfallodatum": "2026-03-16",
        },
        ...
    ]

Tips utifrån filen du visade tidigare (Report_InvoicePurchaseReport):
    Kolumn i källan      ->  Fält i databasen
    ----------------------------------------
    Fakturanr             ->  orderSvea
    Kundnamn               ->  kund
    Restbel                 ->  belopp
    Fakturadatum            ->  fakturadatum
    Förfdat                 ->  forfallodatum
"""

import os
import requests
from datetime import datetime
from typing import Optional


EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_URL", "")
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")

STATUS_MAP = {
    "öppen": "open", "open": "open", "ny": "open", "obetald": "open",
    "pågående": "progress", "progress": "progress", "under utredning": "progress",
    "löst": "resolved", "resolved": "resolved", "avslutad": "resolved",
    "stängd": "closed", "closed": "closed", "betald": "closed",
}


def normalize_order(value) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return s.rstrip("0").rstrip(".") if s.endswith(".0") else s


def parse_date(value) -> str:
    """Konverterar diverse datumformat till YYYY-MM-DD. Returnerar '' om okänt."""
    if not value:
        return ""
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def fetch_external_data() -> list[dict]:
    """
    TODO: Byt ut denna stub mot ett riktigt anrop till din externa källa.

    Exempel om källan är ett JSON-API:

        response = requests.get(
            EXTERNAL_API_URL,
            headers={"Authorization": f"Bearer {EXTERNAL_API_KEY}"},
            timeout=30,
        )
        response.raise_for_status()
        raw_rows = response.json()["data"]

        return [
            {
                "orderSvea": normalize_order(row["Fakturanr"]),
                "orderHemfint": "",
                "kund": row.get("Kundnamn", "").strip(),
                "belopp": str(row.get("Restbel", "")).strip(),
                "status": STATUS_MAP.get(str(row.get("Status", "")).lower(), "open"),
                "fakturadatum": parse_date(row.get("Fakturadatum")),
                "forfallodatum": parse_date(row.get("Förfdat")),
            }
            for row in raw_rows
        ]
    """
    if not EXTERNAL_API_URL:
        # Ingen källa konfigurerad ännu — returnera tom lista så resten av
        # systemet fungerar utan att krascha.
        return []

    response = requests.get(
        EXTERNAL_API_URL,
        headers={"Authorization": f"Bearer {EXTERNAL_API_KEY}"} if EXTERNAL_API_KEY else {},
        timeout=30,
    )
    response.raise_for_status()
    raw_rows = response.json()

    return [
        {
            "orderSvea": normalize_order(row.get("Fakturanr") or row.get("orderSvea")),
            "orderHemfint": normalize_order(row.get("orderHemfint")),
            "kund": str(row.get("Kundnamn") or row.get("kund") or "").strip(),
            "belopp": str(row.get("Restbel") or row.get("belopp") or "").strip(),
            "status": STATUS_MAP.get(str(row.get("Status") or row.get("status") or "").lower(), "open"),
            "fakturadatum": parse_date(row.get("Fakturadatum") or row.get("fakturadatum")),
            "forfallodatum": parse_date(row.get("Förfdat") or row.get("forfallodatum")),
        }
        for row in raw_rows
    ]
