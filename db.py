"""
db.py — All kommunikation med Supabase (Postgres) går genom denna fil.

Frontend och main.py ska ALDRIG prata med Supabase direkt — allt går via
get/set-funktionerna här. Det gör det enkelt att byta databas senare
(SQLite, MySQL, etc.) utan att röra resten av koden.

Tabellschema att skapa i Supabase (SQL Editor):

    create table cases (
        id text primary key,
        "orderSvea" text default '',
        "orderHemfint" text default '',
        kund text default '',
        belopp text default '',
        status text default 'open',
        fakturadatum text default '',
        forfallodatum text default '',
        created bigint,
        updated bigint,
        history jsonb default '[]'::jsonb
    );

    -- Index för snabbare dubblettkontroll och sökning
    create index idx_cases_order_svea on cases ("orderSvea");
    create index idx_cases_order_hemfint on cases ("orderHemfint");

    -- Rekommenderat: unika index på DB-nivå så att två samtidiga requests
    -- aldrig kan skapa dubbletter (applikationens order_exists()-kontroll
    -- skyddar inte mot en race condition på egen hand).
    create unique index idx_cases_order_svea_unique
        on cases ("orderSvea") where "orderSvea" <> '';
    create unique index idx_cases_order_hemfint_unique
        on cases ("orderHemfint") where "orderHemfint" <> '';
"""

import os
import time
import uuid
import logging
from typing import Any, Optional

from supabase import create_client, Client
from dotenv import load_dotenv

from models import CaseCreate, CaseUpdate

load_dotenv()

logger = logging.getLogger("fakturahantering.db")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]  

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

TABLE = "cases"


class DatabaseError(Exception):
    """Wrappar alla databasfel så att main.py kan hantera dem enhetligt
    istället för att låta ett Supabase-undantag studsa upp till klienten."""


class CaseNotFoundError(Exception): # Felhantering för ärenden som inte finns i databasen
    """Ärendet med angivet ID hittades inte."""


def _new_id() -> str: # Genererar ett nytt unikt ID för ett ärende. Använder UUID4 och tar de första 12 tecknen.
    return uuid.uuid4().hex[:12]


def _now_ms() -> int: #Gererar nuvarande tid i millisekunder. Används för att sätta created/updated-tidsstämplar
    return int(time.time() * 1000)


def _run(query, action: str): 
    """Kör en Supabase-query och normaliserar fel till DatabaseError,
    med loggning, så att varje anropsställe inte behöver egen try/except statement."""
    try:
        return query.execute()
    except Exception as e:
        logger.error(f"Databasfel vid {action}: {e}")
        raise DatabaseError(f"Databasfel vid {action}") from e


# ─── READ DATA ──────────────────────────────────────────────────────────────────

def list_cases( #Gererar en lista med ärenden från databasen, med valfria filter för status, källa, sökord och förfallodatum.
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    overdue: Optional[bool] = None,
) -> list[dict]:
    query = supabase.table(TABLE).select("*")

    if status:
        query = query.eq("status", status)

    result = _run(query.order("created", desc=True), "list_cases")
    rows = result.data or []

    # Filter som är enklare att göra i Python än i SQL (matchar frontend-logiken med dubblettkontroll och sökning)
    if source == "svea":
        rows = [r for r in rows if r.get("orderSvea")]
    elif source == "hemfint":
        rows = [r for r in rows if r.get("orderHemfint")]
    elif source == "both":
        rows = [r for r in rows if r.get("orderSvea") and r.get("orderHemfint")]

    if search:
        s = search.lower()
        rows = [
            r for r in rows
            if s in (r.get("orderSvea") or "").lower()
            or s in (r.get("orderHemfint") or "").lower()
            or s in (r.get("kund") or "").lower()
        ]

    if overdue:
        today = _now_ms()
        rows = [
            r for r in rows
            if r.get("forfallodatum")
            and r.get("status") not in ("resolved", "closed")
            and _date_to_ms(r["forfallodatum"]) < today
        ]

    return rows


def get_case(case_id: str) -> Optional[dict]: # Hämtar ett enskilt ärende från databasen baserat på dess ID. Returnerar None om ärendet inte hittas.
    result = _run(supabase.table(TABLE).select("*").eq("id", case_id), "get_case")
    return result.data[0] if result.data else None


def order_exists(field: str, value: str, exclude_id: Optional[str] = None) -> bool: 
    """Kollar om ett ordernummer redan finns. Ange exclude_id vid uppdatering
    av ett befintligt ärende, så att ärendet inte krockar med sig självt."""
    query = supabase.table(TABLE).select("id").eq(field, value)
    if exclude_id:
        query = query.neq("id", exclude_id)
    result = _run(query, "order_exists")
    return len(result.data) > 0


# ─── CREATE CASE ────────────────────────────────────────────────────────────────

def create_case(payload: CaseCreate) -> dict: #Skapar ett nytt ärende i databasen baserat på payload. Om payload.note inte är None, läggs en anteckning till i ärendets historik.
    now = _now_ms()
    history = []
    if payload.note:
        history.append({"ts": now, "text": payload.note, "type": "skapad"})

    row: dict[str, Any] = {
        "id": _new_id(),
        "orderSvea": payload.orderSvea or "",
        "orderHemfint": payload.orderHemfint or "",
        "kund": payload.kund or "",
        "belopp": payload.belopp or "",
        "status": payload.status,
        "fakturadatum": payload.fakturadatum or "",
        "forfallodatum": payload.forfallodatum or "",
        "created": now,
        "updated": now,
        "history": history,
    }
    result = _run(supabase.table(TABLE).insert(row), "create_case")
    return result.data[0]


# ─── UPDATE CASE ────────────────────────────────────────────────────────────────

def update_case(case_id: str, payload: CaseUpdate) -> dict: #Uppdaterar ett befintligt ärende i databasen baserat på dess ID. Om ärendet inte hittas, kastas ett CaseNotFoundError.
    existing = get_case(case_id)
    if existing is None:
        raise CaseNotFoundError(case_id)

    updates: dict[str, Any] = {"updated": _now_ms()}

    for field in ("orderSvea", "orderHemfint", "kund", "belopp", "status", "fakturadatum", "forfallodatum"): #Går igenom alla fält som kan uppdateras och lägger till dem i updates-dictionaryn om de inte är None.
        value = getattr(payload, field)
        if value is not None:
            updates[field] = value

    if payload.note: #Lägger till en ny anteckning i ärendets historik om payload.note inte är None. Historiken lagras som en lista av dictionaries med tidsstämpel, text och typ.
        history = existing.get("history") or []
        history.append({"ts": _now_ms(), "text": payload.note, "type": None})
        updates["history"] = history

    result = _run(supabase.table(TABLE).update(updates).eq("id", case_id), "update_case") #Kör en uppdateringsquery mot databasen med de samlade uppdateringarna. Om ärendet inte hittas, kastas ett CaseNotFoundError.
    return result.data[0]


def bulk_upsert_from_external(rows: list[dict]) -> dict:
    """
    Tar emot rader (redan normaliserade, se external_source.py) och
    skriver in nya ärenden. Hoppar över rader vars ordernummer redan finns,
    precis som frontends gamla doImport()-logik gjorde.
    """
    all_cases = list_cases()  # en enda hämtning (tidigare hämtades allt två gånger)
    existing_svea = {r["orderSvea"] for r in all_cases if r.get("orderSvea")}
    existing_hemfint = {r["orderHemfint"] for r in all_cases if r.get("orderHemfint")}

    to_insert: list[dict[str, Any]] = [] #Skapar en lista med dictionaries som ska infogas i databasen. Varje dictionary representerar ett nytt ärende med alla nödvändiga fält.
    added, skipped = 0, 0
    now = _now_ms()

    for row in rows: #Går igenom varje rad som skickats in och kontrollerar om ordernumret redan finns i databasen. Om det inte finns, läggs raden till i to_insert-listan. Om det redan finns, ökas skipped-räknaren.
        svea = row.get("orderSvea", "")
        hemfint = row.get("orderHemfint", "")

        if not svea and not hemfint:
            skipped += 1
            continue
        if svea and svea in existing_svea:
            skipped += 1
            continue
        if hemfint and hemfint in existing_hemfint:
            skipped += 1
            continue

        to_insert.append({ #Skapar en ny dictionary med alla nödvändiga fält för det nya ärendet och lägger till den i to_insert-listan. Fälten inkluderar ett nytt unikt ID, ordernummer, kund, belopp, status, fakturadatum, förfallodatum, skapad- och uppdaterad-tidsstämpel samt en tom historiklista.
            "id": _new_id(),
            "orderSvea": svea,
            "orderHemfint": hemfint,
            "kund": row.get("kund", ""),
            "belopp": row.get("belopp", ""),
            "status": row.get("status", "open"),
            "fakturadatum": row.get("fakturadatum", ""),
            "forfallodatum": row.get("forfallodatum", ""),
            "created": now,
            "updated": now,
            "history": [],
        })
        if svea:
            existing_svea.add(svea)
        if hemfint:
            existing_hemfint.add(hemfint)
        added += 1

    if to_insert:
        _run(supabase.table(TABLE).insert(to_insert), "bulk_upsert_from_external") #Kör en infogningsquery mot databasen med alla nya ärenden som samlats i to_insert-listan.

    return {"added": added, "updated": 0, "skipped": skipped}
def bulk_import_manual(rows: list[dict]) -> dict:
    # [NYTT] Hela denna funktion fanns inte tidigare. Motsvarar backend-sidan
    # av det som tidigare gjordes helt i webbläsaren (doImport() i
    # index.html), fast med dubblettkontroll mot den riktiga databasen
    # istället för bara webbläsarens minne.
    """
    Tar emot rader som redan kolumnmappats manuellt i UI (användaren laddade
    upp en Excel-fil och valde vilka kolumner som motsvarar vilka fält — se
    doImport() i index.html). Till skillnad från bulk_upsert_from_external
    (den automatiska dagliga importen) särskiljer denna funktion:
      - "dupes"   -> ordernumret finns redan (i databasen eller tidigare i
                     samma fil)
      - "skipped" -> raden saknade helt ordernummer
    eftersom frontend visar dessa som två separata siffror till användaren,
    precis som den gamla rent lokala doImport()-funktionen gjorde.
    """
    all_cases = list_cases()
    existing_svea = {r["orderSvea"] for r in all_cases if r.get("orderSvea")}
    existing_hemfint = {r["orderHemfint"] for r in all_cases if r.get("orderHemfint")}
 
    to_insert: list[dict[str, Any]] = []
    added, skipped, dupes = 0, 0, 0
    now = _now_ms()
 
    for row in rows:
        svea = row.get("orderSvea") or ""
        hemfint = row.get("orderHemfint") or ""
 
        if not svea and not hemfint:
            skipped += 1
            continue
        if svea and svea in existing_svea:
            dupes += 1
            continue
        if hemfint and hemfint in existing_hemfint:
            dupes += 1
            continue
 
        history = []
        note = row.get("note")
        if note:
            history.append({"ts": now, "text": note, "type": "import"})
 
        to_insert.append({
            "id": _new_id(),
            "orderSvea": svea,
            "orderHemfint": hemfint,
            "kund": row.get("kund", "") or "",
            "belopp": row.get("belopp", "") or "",
            "status": row.get("status") or "open",
            "fakturadatum": row.get("fakturadatum", "") or "",
            "forfallodatum": row.get("forfallodatum", "") or "",
            "created": now,
            "updated": now,
            "history": history,
        })
        if svea:
            existing_svea.add(svea)
        if hemfint:
            existing_hemfint.add(hemfint)
        added += 1
 
    if to_insert:
        _run(supabase.table(TABLE).insert(to_insert), "bulk_import_manual")
 
    return {"added": added, "skipped": skipped, "dupes": dupes}

                     


     


# ─── DELETE ────────────────────────────────────────────────────────────────

def delete_case(case_id: str) -> None:
    _run(supabase.table(TABLE).delete().eq("id", case_id), "delete_case")


# ─── STATS ─────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    rows = list_cases()
    today = _now_ms()

    total = len(rows) #Gererar statistik över ärenden i databasen, inklusive totalt antal, öppna, pågående, lösta och förfallna ärenden. Förfallna ärenden definieras som de som har ett förfallodatum som är tidigare än dagens datum och som inte är markerade som lösta eller stängda.
    open_ = sum(1 for r in rows if r["status"] == "open")
    progress = sum(1 for r in rows if r["status"] == "progress")
    resolved = sum(1 for r in rows if r["status"] in ("resolved", "closed"))
    overdue = sum(
        1 for r in rows
        if r.get("forfallodatum")
        and r["status"] not in ("resolved", "closed")
        and _date_to_ms(r["forfallodatum"]) < today
    )

    return {
        "total": total,
        "open": open_,
        "progress": progress,
        "resolved": resolved,
        "overdue": overdue,
    }


def _date_to_ms(date_str: str) -> int: #Funktion som konverterar ett datum i formatet 'YYYY-MM-DD' till millisekunder sedan epoken (1970-01-01). 
    """Konverterar 'YYYY-MM-DD' till millisekunder för enkel jämförelse."""
    from datetime import datetime
    try:
        return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp() * 1000)
    except (ValueError, TypeError):
        return 0