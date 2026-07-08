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
import io
import logging
import os
import requests
from datetime import datetime
from typing import Optional

import requests
import pandas as pd

from column_mapper import map_columns

logger = logging.getLogger("fakturahantering.external_source")

EXTERNAL_API_URL = os.environ.get("EXTERNAL_API_URL", "")
EXTERNAL_API_KEY = os.environ.get("EXTERNAL_API_KEY", "")

STATUS_MAP = {
    "öppen": "open", "open": "open", "ny": "open", "obetald": "open",
    "pågående": "progress", "progress": "progress", "under utredning": "progress",
    "löst": "resolved", "resolved": "resolved", "avslutad": "resolved",
    "stängd": "closed", "closed": "closed", "betald": "closed",
}


def normalize_order(value) -> str: #Konverterar ordernummer till sträng och tar bort onödiga decimaler. Returnerar '' om None.
    if value is None:
        return ""
    s = str(value).strip()
    return s.rstrip("0").rstrip(".") if s.endswith(".0") else s


def parse_date(value) -> str:
    """Konverterar diverse datumformat till YYYY-MM-DD. Returnerar '' om okänt."""
    if not value:
        return ""
    #pandas läser ofta in Excel-datum som timestamp/datetime redan
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s or s.lower() == "nat":
        return ""
    
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""

def _rows_from_response(response: requests.Response) -> list[dict]:
    """
    Tolkar svaret från Svea. Avgör om det är en Excel fil eller JSON baserat på content-type och url-ändelse, returnerar alltid en lista av dicts
    """
    content_type = response.headers.get("content-type", "").lower()
    looks_like_excel = (
        "spreadsheet" in content_type
        or "excel" in content_type
        or response.url.lower().endswith((".xls", ".xlsx"))
    )

    if looks_like_excel:
        # Excel-fil
        df = pd.read_excel(io.BytesIO(response.content))

        #Tomma rader kan förekomma i Excel-filer, ta bort dem
        df = df.dropna(how="all")
        return df.to_dict(orient="records") 
    
    # Annars anta att det är JSON
    data = response.json()
    if isinstance(data, dict):
        for key in ("data", "rows", "items","results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        raise ValueError(            
            "Kunde inte hitta en lista med rader i JSON-svaret från Svea "
            f"(nycklar i svaret: {list(data.keys())})"
        )    
    return data


   



def fetch_external_data() -> list[dict]:
    """
    
    Hämtar och normaliserar dagens data från Svea.
 
    Kolumnnamnen mappas DYNAMISKT varje körning (se column_mapper.py) istället
    för att anta fasta kolumnnamn — så en körning där Svea kallar kolumnen
    "Fakturanr" och en annan körning där den kallas "Order-ID" hanteras båda
    utan kodändring.
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
    raw_rows = rows_from_response(response)
    if not raw_rows:
        logger.info("Sveas svar innehöll inga rader denna körning.")
        return []
    
    # Vilka kolumner kom med denna gång och vad motsvarar de i vår datamodell. 
    available_columns = [str (c) for c in raw_rows[0].keys()]
    column_map = map_columns(available_columns)
    logger.info(f"Kolumnmappning från Svea-import: {column_map}")

    unmapped = [field for field, col in column_map.items() if col is None]
    if unmapped:
        logger.warning(
            f"Kunde inte matcha följande kolumner för fälten {unmapped} - dessa fälten "
            f"blir tomma för samtliga raden denna korning. Tillgänliga "
            f"kolumner var_ {available_columns}"
        )
    def _get(row: dict, field: str):
        col = column_map.get(field)
        return row.get(col) if col else None
    result = []
    for row in raw_rows:
        result.append({
            "orderSvea": normalize_order(_get(row, "orderSvea")),
            "orderHemfint": normalize_order(_get(row, "orderHemfint")),
            "kund": str(_get(row, "kund") or "").strip(),
            "belopp": str(_get(row, "belopp") or "").strip(),
            "status": STATUS_MAP.get(str(_get(row, "status") or "").lower(), "open"),
            "fakturadatum": parse_date(_get(row, "fakturadatum")),
            "forfallodatum": parse_date(_get(row, "forfallodatum")),
        })    
    return result     
    



