# Fakturahantering — Python-backend

Data-navet i systemet. Läser in data från en extern källa en gång om dagen,
exponerar CRUD via REST-API (GET/SET) som frontend pratar med, och skriver ut
till xlsx/csv vid dagens slut.

```
Extern källa ──(06:00, dagligen)──> Supabase (Postgres) <──REST API── Frontend
                                           │
                                           └──(23:00, dagligen)──> xlsx / csv
```


## 1. Konfigurera backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```

 `.env` och fyll i:
- `SUPABASE_URL` och `SUPABASE_KEY` 
- `EXTERNAL_API_URL` / `EXTERNAL_API_KEY` när detta givits

## 2. Kör lokalt

```bash
uvicorn main:app --reload
```

API:et igång på `http://localhost:8000`. webbläsaren:
`http://localhost:8000/cases` ska returnera `[]` (tom lista) om databasen är ny.

Interaktiv API-dokumentation (test för endpoints direkt i browsern):
`http://localhost:8000/docs`

## 3. Driftsättning

Rekommendation: **Railway** eller **Render** — båda har gratisnivåer, kopplar
direkt till ett GitHub-repo, och kör `apscheduler`-jobbet (dagligt
import/export) i bakgrunden utan extra konfiguration.

1. Pusha `backend/`-mappen till ett GitHub-repo.
2. Skapa nytt projekt på Railway/Render, koppla repot.
3. Lägg in samma miljövariabler som i `.env` under projektets "Environment
   Variables".
4. Starta. Din publika URL blir t.ex. `https://dittprojekt.up.railway.app`.

## 4. Koppla frontend mot backend

I `fakturahantering.html`, alla -anropen utbytta mot `fetch()` mot
nya API.





## Filöversikt

| Fil                  | Ansvar                                                          |
|-----------------------|------------------------------------------------------------------|
| `main.py`              | FastAPI-app, alla REST-endpoints                                 |
| `models.py`            | Pydantic-modeller (fältnamn matchar frontend exakt)               |
| `db.py`                | All Supabase-kommunikation (CRUD)                                |
| `external_source.py`   | Hämtar/normaliserar data från din externa källa (fyll i när redo) |
| `exporter.py`          | Skriver xlsx/csv-filer 
|
| `scheduler.py`  
| `column_mapper.py`     | Mappar kolumner dynamiskt sammma matchingslogistik som i frontend.
| `auth.py`              | multi-user stöd och kryptering. 
| Dagligt schema: import 06:00, export 23:00                        |
