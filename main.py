"""
Fakturahantering — Python-backend (FastAPI + Supabase)
=========================================================

Detta är "data-navet" i systemet:

  Extern källa (API) ──(1x/dag)──> Supabase (Postgres) <──CRUD (GET/SET)── Frontend (HTML/JS)
                                          │
                                          └──(vid dagens slut)──> xlsx / csv-export

Arkitektur i korthet:
  - main.py          startar FastAPI-appen och definierar alla REST-endpoints
  - db.py            sköter all kommunikation med Supabase (CRUD mot tabellen "cases")
  - external_source.py  hämtar/parsar data från den externa källan (stub tills du
                         fyller i riktig logik)
  - exporter.py       skriver databasens innehåll till .xlsx och .csv
  - scheduler.py      kör det dagliga jobbet automatiskt (import på morgonen,
                       export på kvällen)
  - models.py         Pydantic-modeller (definierar fälten i ett "ärende")

Kör lokalt:
    pip install -r requirements.txt
    cp .env.example .env        # fyll i dina Supabase-uppgifter
    uvicorn main:app --reload

Endpoints (GET/SET-metoder mot frontend):
    GET    /cases                  -> hämta alla ärenden (med valfria filter)
    GET    /cases/{id}             -> hämta ett ärende
    POST   /cases                  -> skapa nytt ärende
    PUT    /cases/{id}             -> uppdatera ärende (skriver även historik)
    DELETE /cases/{id}             -> ta bort ärende
    GET    /stats                  -> sammanställd statistik för dashboard
    POST   /import/run             -> kör import från extern källa manuellt (utöver dagligt schema)
    GET    /export/xlsx            -> ladda ner aktuell databas som .xlsx
    GET    /export/csv             -> ladda ner aktuell databas som .csv
"""
import os 
import logging

from fastapi import FastAPI, HTTPException, Query, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional
import logging

from models import (  #Nya modeller som stöder login och cases/ import- manual
    CaseCreate, CaseUpdate, CaseOut,
    Loginrequest, LoginResponse,
    ManualImportRequest, ManualImportResult,
)    

import db
from db import DatabaseError, CaseNotFoundError # Dras ej lokalt längre istället importeras från db.py  
import exporter
from external_source import fetch_external_data
from scheduler import start_scheduler

from auth import require_auth, verify_password, create_token, check_configured


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fakturahantering")

app = FastAPI(title="Fakturahantering API", version="1.0.0")

# ─── GLOBAL EXCEPTION HANDLERS ───────────────────────────────────────────────────────────────────
@app.exception_handler(db.DatabaseError)

def handle_database_error(request: Request, exc: DatabaseError): #Metod för att hantera databasfel. Loggar felet och returnerar ett 503-svar till klienten.
    logger.error(f"Database error vid {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": "Databasfel. Kontakta administratören."},
    )

@app.exception_handler(db.CaseNotFoundError)

def handle_case_not_found_error(request: Request, exc: CaseNotFoundError): #Metod för att hantera ärendet hittades inte-fel. Loggar felet och returnerar ett 404-svar till klienten.
    logger.warning(f"Ärendet hittades inte vid {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=404,
        content={"detail": "Ärendet hittades inte."},
    )
    
    


# ─── CORS ───────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS= [ #Variabel för att tillåta frontend (annan origin, t.ex. GitHub Pages eller lokal fil) att anropa API:et.
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "*").split(",")
    if origin.strip()
]    


# Tillåt frontend (annan origin, t.ex. GitHub Pages eller lokal fil) att anropa API:et.
# Byt ut "*" mot den riktiga domän i produktion.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Startar det dagliga schemat (import på morgonen, export på kvällen)."""
    start_scheduler()

    try:
        check_configured()
    except RuntimeError as e:
        logger.warning(f"OBS: autentiseringe är inte korrekt konfigurerad ännu:{e}")        
    logger.info("Backend startad. Dagligt schema aktiverat.")

# Endpoint utan data, används av load balancer / health check för att se om appen är igång.
@app.get("/health")
def health():
    return {"status": "ok"}

# ─── Inloggning ───────────────────────────────────────────────────────────────
@app.post("/login", response_model=LoginResponse)
def login(payload: Loginrequest):
    """
     Loggar in en användare (se manage_users.py för hur användare skapas) och
    returnerar en signerad, tidsbegränsad sessionstoken. Frontend sparar
    token och skickar med den som `Authorization: Bearer <token>` på alla
    efterföljande anrop mot skyddade endpoints.
    """
    try:
        ok = verify_password(payload.username, payload.password)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    if not ok:
        raise HTTPException(status_code=401, detail="Felaktigt användarnamn eller lösenord")
    token = create_token(payload.username)
    return {"token": token, "username": payload.username}
    
    
    


# ─── CRUD: ärenden ────────────────────────────────────────────────────────────

@app.get("/cases", response_model=list[CaseOut])
def get_cases(
    status: Optional[str] = Query(None, description="Filtrera på status: open/progress/resolved/closed"),
    source: Optional[str] = Query(None, description="Filtrera på källa: svea/hemfint/both"),
    search: Optional[str] = Query(None, description="Sök i ordernr eller kundnamn"),
    overdue: Optional[bool] = Query(None, description="Visa bara förfallna"),
    username: str = Depends(require_auth),
):
    """Hämta alla ärenden, med samma filtermöjligheter som frontend redan har."""
    return db.list_cases(status=status, source=source, search=search, overdue=overdue)


@app.get("/cases/{case_id}", response_model=CaseOut)
def get_case(case_id: str, username: str = Depends(require_auth)): # auth krav
    case = db.get_case(case_id)
    if not case:
        raise CaseNotFoundError(case_id) #specificerar att ärendet inte hittades, vilket hanteras av exception handlern ovan.
    return case


@app.post("/cases", response_model=CaseOut, status_code=201)
def create_case(payload: CaseCreate, username: str = Depends(require_auth)): # auth krav
    """Skapa nytt ärende manuellt (motsvarar 'Lägg till ärende manuellt' i UI)."""
    if payload.orderSvea and db.order_exists("orderSvea", payload.orderSvea):
        raise HTTPException(status_code=409, detail="Svea-ordernumret finns redan")
    if payload.orderHemfint and db.order_exists("orderHemfint", payload.orderHemfint):
        raise HTTPException(status_code=409, detail="Hemfint-ordernumret finns redan")
    return db.create_case(payload)


@app.put("/cases/{case_id}", response_model=CaseOut)
def update_case(case_id: str, payload: CaseUpdate, username: str=Depends(require_auth)): # auth krav
    """Uppdatera ärende. Om 'note' skickas med läggs den till i historiken."""
    case = db.get_case(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    
    if payload.orderSvea and db.order_exists("orderSvea", payload.orderSvea, exclude_id=case_id):
        raise HTTPException(status_code=409, detail="Svea-ordernumret finns redan på ett annat ärende")
    if payload.orderHemfint and db.order_exists("orderHemfint", payload.orderHemfint, exclude_id=case_id):
        raise HTTPException(status_code=409, detail="Hemfint-ordernumret finns redan på ett annat ärende")
    
    #Db.update_case hanterar själva uppdateringen och historiken. Kastar själv CaseNotFoundError om ärendet skulle försvinna mellan kontrollen och detta anrop Om 'note' skickas med läggs den till i historiken.
    return db.update_case(case_id, payload)


@app.delete("/cases/{case_id}", status_code=204) # Delete endpoint för att ta bort ett ärende. Returnerar 204 No Content 
def delete_case(case_id: str, username: str = Depends(require_auth)): # auth krav
    case = db.get_case(case_id)
    if not case:
        raise CaseNotFoundError(case_id)
    db.delete_case(case_id)


# ─── Manuell Excel-import (kolumnmappad i UI) ─────────────────────────────────
# [NYTT] Hela detta avsnittet (POST /cases/import-manual) fanns inte
# tidigare. Ersätter logik som tidigare låg helt lokalt i doImport() i
# index.html - se db.bulk_import_manual() för själva dubblettkontrollen.

@app.post("/cases/import-manual", response_model=ManualImportResult)
def import_manual(payload: ManualImportRequest, username: str = Depends(require_auth)): # auth krav
    """
    Tar emot en lista med ärenden (från frontend) och försöker lägga till dem
    i databasen. Returnerar statistik över hur många som lades till, uppdaterades
    eller hoppades över (dubbletter).
    """
    rows = [r.model_dump() for r in payload.rows]
    return db.bulk_import_manual(rows)

# ─── Statistik (för dashboard-korten överst) ──────────────────────────────────

@app.get("/stats")
def get_stats(username: str = Depends(require_auth)): # auth krav
    return db.get_stats()


# ─── Import från extern källa ─────────────────────────────────────────────────

@app.post("/import/run")
def run_import(username: str = Depends(require_auth)): # auth krav
    """
    Triggar import från den externa källan manuellt (utöver det dagliga
    automatiska schemat). Användbart för en 'Importera nu'-knapp i UI.
    """
    rows = fetch_external_data()
    result = db.bulk_upsert_from_external(rows)
    return {
        "message": f"{result['added']} nya, {result['updated']} uppdaterade, "
                   f"{result['skipped']} hoppade över.",
        **result,
    }


# ─── Export till xlsx / csv ───────────────────────────────────────────────────

@app.get("/export/xlsx")
def export_xlsx(username: str = Depends(require_auth)): # auth krav
    path = exporter.export_to_xlsx(db.list_cases())
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="fakturor.xlsx",
    )


@app.get("/export/csv")
def export_csv(username: str = Depends(require_auth)): # auth krav
    path = exporter.export_to_csv(db.list_cases())
    return FileResponse(path, media_type="text/csv", filename="fakturor.csv")
