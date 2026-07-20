"""
auth.py — Lösenordsbaserad autentisering för API:et, med stöd för flera
namngivna användare.

Lösenord lagras ALDRIG i klartext, varken i kod eller i databasen — bara ett
saltat hash (PBKDF2-HMAC-SHA256, 200 000 iterationer) per användare, i
miljövariabeln APP_USERS.

Vid lyckad inloggning (POST /login med {"username", "password"}) utfärdas en
signerad, tidsbegränsad session-token (giltig i TOKEN_TTL_SECONDS) som även
innehåller vem som loggade in. Frontend skickar med token i
`Authorization: Bearer <token>` på alla efterföljande anrop mot API:et.
Alla skyddade endpoints i main.py använder `Depends(require_auth)`.

Ingen extern paketberoende krävs — bygger enbart på Python-standardbiblioteket
(hashlib, hmac, base64, json), så inget behöver läggas till i requirements.txt.

── Format på APP_USERS ─────────────────────────────────────────────────────

    APP_USERS=namn1:salt1:hash1,namn2:salt2:hash2,...

Varje användare är en "namn:salt:hash"-grupp, flera användare separeras med
komma. Du behöver ALDRIG skriva detta för hand — kör `manage_users.py` (i
samma mapp som denna fil):

    python manage_users.py

Skriptet frågar efter användarnamn + lösenord och skriver ut en
färdig APP_USERS-rad att klistra in i din `.env` (eller lägger till en
ny användare i en befintlig rad om du kör det igen).

 `SECRET_KEY` måste sättas till en slumpad hemlig sträng, en gång:

    python -c "import os; print(os.urandom(32).hex())"

Se `.env.example` för samtliga variabler.
"""

import os
import hmac
import time
import base64
import json
import hashlib
from typing import Optional, Dict, Tuple

from fastapi import Header, HTTPException

SECRET_KEY = os.environ.get("SECRET_KEY", "")

TOKEN_TTL_SECONDS = 12 * 60 * 60  # session giltig i 12 timmar
PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    ).hex()


def _parse_users() -> Dict[str, Tuple[str, str]]:
    """
    Läser APP_USERS-miljövariabeln (format: 'namn:salt:hash,namn2:salt2:hash2')
    och returnerar { "namn": (salt, hash), ... }. Läses vid varje anrop (inte
    cachead) så att en omstart av processen räcker efter att man lagt till en
    användare i miljövariablerna.
    """
    raw = os.environ.get("APP_USERS", "") #Skapar en dictionary med användarnamn som nycklar och tuple (salt, hash) som värden från APP_USERS-miljövariabeln. Om variabeln är tom returneras en tom dictionary.
    users: Dict[str, Tuple[str, str]] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3:
            continue  # hoppar tyst över felformaterade poster
        username, salt, pwd_hash = parts
        users[username] = (salt, pwd_hash) #sätter in användarnamn som nyckel och (salt, hash) som värde i users-dictionaryn.
    return users


def _check_config() -> None: #Kontrollerar att nödvändiga miljövariabler är satta (SECRET_KEY och APP_USERS). Om någon saknas, kastas ett RuntimeError med en beskrivande felmeddelande.
    if not SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY måste vara satt som miljövariabel innan inloggning "
            "fungerar — se auth.py (docstring överst i filen)."
        )
    if not _parse_users():
        raise RuntimeError(
            "Ingen användare är konfigurerad. Kör `python manage_users.py` "
            "för att skapa en, och lägg in den rad den skriver ut som "
            "APP_USERS i din .env."
        )


def verify_password(username: str, password: str) -> bool:
    """Jämför ett inskickat lösenord mot det lagrade saltade hashet för den
    angivna användaren. Returnerar False både om användaren inte finns och
    om lösenordet är fel (avslöjar inte vilketdera för anroparen)."""
    _check_config()
    users = _parse_users()
    entry = users.get(username)
    if not entry:
        return False
    salt, stored_hash = entry
    computed = hash_password(password, salt)
    return hmac.compare_digest(computed, stored_hash)


def _sign(payload_b64: str) -> str:
    return hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()


def create_token(username: str) -> str: #Skapar en signerad token med utgångstid och inloggat användarnamn. Formatet är payload.signatur
    """Skapar en signerad token med utgångstid och inloggat användarnamn.
    Formatet är payload.signatur, liknar en förenklad JWT men kräver inga
    extra paket."""
    _check_config() #funktion som kontrollerar att nödvändiga miljövariabler är satta (SECRET_KEY och APP_USERS). Om någon saknas, kastas ett RuntimeError med en beskrivande felmeddelande.
    payload = {"sub": username, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def _decode_token(token: str) -> Optional[dict]: #Dekrypterar och verifierar en token. Returnerar payload som dict om giltig, annars None.
    _check_config()
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(payload_b64), sig):
        return None  # signaturen matchar inte -> manipulerad eller ogiltig token
    try:
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()))
    except Exception:
        return None
    if payload.get("exp", 0) <= time.time():
        return None  # token har gått ut
    return payload


def verify_token(token: str) -> bool: #Verifierar om en token är giltig (signatur och utgångstid). Returnerar en boolean True om giltig, annars False. 
    return _decode_token(token) is not None

def check_configured() -> None: #Kontrollerar att nödvändiga miljövariabler är satta (SECRET_KEY och APP_USERS). Om någon saknas, kastas ett RuntimeError med en beskrivande felmeddelande.

_check_config()

def require_auth(authorization: Optional[str] = Header(None)) -> str: 
    """FastAPI-dependency. Lägg till `username: str = Depends(require_auth)`
    på varje endpoint som ska kräva inloggning — returnerar det inloggade
    användarnamnet (från tokenens 'sub'-fält) om token är giltig."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Inte inloggad")
    token = authorization[len("Bearer "):]
    payload = _decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Sessionen har gått ut, logga in igen")
    return payload.get("sub", "")