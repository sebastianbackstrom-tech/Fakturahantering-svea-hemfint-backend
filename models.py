"""
Pydantic-modeller — definierar exakt samma fält som frontend redan använder
(orderSvea, orderHemfint, kund, belopp, status, fakturadatum, förfallodatum, history).

Genom att hålla fältnamnen identiska med JavaScript-koden slipper du skriva
om frontend mer än att byta ut fetch-anropen mot ditt nya API.
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal


Status = Literal["open", "progress", "resolved", "closed"]


class HistoryItem(BaseModel):
    ts: int                      # millisekunder sedan epoch (samma som Date.now() i JS)
    text: str
    type: Optional[str] = None   # t.ex. "import", "skapad", eller None för manuell uppdatering


class CaseBase(BaseModel):
    orderSvea: Optional[str] = ""
    orderHemfint: Optional[str] = ""
    kund: Optional[str] = ""
    belopp: Optional[str] = ""
    status: Status = "open"
    fakturadatum: Optional[str] = ""     # format: YYYY-MM-DD
    forfallodatum: Optional[str] = ""    # format: YYYY-MM-DD


class CaseCreate(CaseBase):
    note: Optional[str] = None  # om satt, skapas en första historikpost


class CaseUpdate(BaseModel):
    orderSvea: Optional[str] = None
    orderHemfint: Optional[str] = None
    kund: Optional[str] = None
    belopp: Optional[str] = None
    status: Optional[Status] = None
    fakturadatum: Optional[str] = None
    forfallodatum: Optional[str] = None
    note: Optional[str] = None  # om satt, läggs den till som ny historikpost


class CaseOut(CaseBase):
    id: str
    created: int
    updated: int
    history: list[HistoryItem] = Field(default_factory=list)

# ─── Auth ────────────────────────────────────────────────────────────────────
# klasserna används av main.py nya POST login-endpoint. 
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str


# ─── Manuell Excel-import (kolumnmappad i UI, se index.html) ────────────────

# Låg tidigare lokalt i index.html doImport() funktionen ersätter den med nya main.py POST /cases/import-manual

class ManualImportRow(CaseBase):
    note: Optional[str] = None  # om satt, läggs den till som ny historikpost

class ManualImportRequest(BaseModel):
    rows: list[ManualImportRow]

class ManualImportResult(BaseModel):
    added: int
    skipped: int
    dupes: int
    

