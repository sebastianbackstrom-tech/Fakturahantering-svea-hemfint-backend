"""
exporter.py — Skriver databasens innehåll till .xlsx och .csv.

Körs antingen manuellt via GET /export/xlsx eller /export/csv, eller
automatiskt vid dagens slut via scheduler.py.
"""

import os
import csv
from datetime import datetime

import pandas as pd

OUTPUT_DIR = os.environ.get("EXPORT_DIR", "./exports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

STATUS_LABELS = {
    "open": "Öppen",
    "progress": "Pågående",
    "resolved": "Löst",
    "closed": "Stängd",
}


def _to_rows(cases: list[dict]) -> list[dict]:
    """Samma kolumner som den ursprungliga exportCSV() i frontend hade."""
    rows = []
    for c in cases:
        history = c.get("history") or []
        last_update = (
            datetime.fromtimestamp(history[-1]["ts"] / 1000).strftime("%Y-%m-%d")
            if history else ""
        )
        rows.append({
            "Ordernr Svea": c.get("orderSvea", ""),
            "Ordernr Hemfint": c.get("orderHemfint", ""),
            "Kund": c.get("kund", ""),
            "Belopp": c.get("belopp", ""),
            "Status": STATUS_LABELS.get(c.get("status"), c.get("status", "")),
            "Fakturadatum": c.get("fakturadatum", ""),
            "Förfallodatum": c.get("forfallodatum", ""),
            "Skapad": datetime.fromtimestamp(c["created"] / 1000).strftime("%Y-%m-%d") if c.get("created") else "",
            "Senast uppdaterad": last_update,
            "Antal kommentarer": len(history),
        })
    return rows


def export_to_xlsx(cases: list[dict]) -> str:
    rows = _to_rows(cases)
    df = pd.DataFrame(rows)
    filename = f"fakturor_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    path = os.path.join(OUTPUT_DIR, filename)
    df.to_excel(path, index=False, engine="openpyxl")
    return path


def export_to_csv(cases: list[dict]) -> str:
    rows = _to_rows(cases)
    filename = f"fakturor_{datetime.now().strftime('%Y-%m-%d')}.csv"
    path = os.path.join(OUTPUT_DIR, filename)

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        else:
            f.write("")

    return path
