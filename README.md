# Fakturahantering — Python-backend

Data-navet i systemet. Läser in data från en extern källa en gång om dagen,
exponerar CRUD via REST-API (GET/SET) som frontend pratar med, och skriver ut
till xlsx/csv vid dagens slut.

```
Extern källa ──(06:00, dagligen)──> Supabase (Postgres) <──REST API── Frontend
                                           │
                                           └──(23:00, dagligen)──> xlsx / csv
```

## 1. Skapa Supabase-projekt

1. Gå till [supabase.com](https://supabase.com) och skapa ett nytt projekt (gratisnivå räcker).
2. Öppna **SQL Editor** och kör:

```sql
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

create index idx_cases_order_svea on cases ("orderSvea");
create index idx_cases_order_hemfint on cases ("orderHemfint");
```

3. Gå till **Project Settings > API** och kopiera `Project URL` och
   `service_role`-nyckeln (inte `anon`-nyckeln — service_role behövs för att
   backend ska få full CRUD-åtkomst).

## 2. Konfigurera backend

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```

Öppna `.env` och fyll i:
- `SUPABASE_URL` och `SUPABASE_KEY` (från steg 1)
- `EXTERNAL_API_URL` / `EXTERNAL_API_KEY` när du har den informationen

## 3. Kör lokalt

```bash
uvicorn main:app --reload
```

API:et är nu igång på `http://localhost:8000`. Testa i webbläsaren:
`http://localhost:8000/cases` ska returnera `[]` (tom lista) om databasen är ny.

Interaktiv API-dokumentation (testa endpoints direkt i browsern):
`http://localhost:8000/docs`

## 4. Driftsättning (när du är redo)

Rekommendation: **Railway** eller **Render** — båda har gratisnivåer, kopplar
direkt till ett GitHub-repo, och kör `apscheduler`-jobbet (dagligt
import/export) i bakgrunden utan extra konfiguration.

1. Pusha `backend/`-mappen till ett GitHub-repo.
2. Skapa nytt projekt på Railway/Render, koppla repot.
3. Lägg in samma miljövariabler som i `.env` under projektets "Environment
   Variables".
4. Starta. Din publika URL blir t.ex. `https://dittprojekt.up.railway.app`.

## 5. Koppla frontend mot backend

I `fakturahantering.html`, byt ut `localStorage`-anropen mot `fetch()` mot
ditt nya API. Exempel på de viktigaste bytena:

```javascript
const API_URL = 'https://dittprojekt.up.railway.app'; // eller http://localhost:8000 vid lokal test

// Hämta alla ärenden (ersätter loadData())
async function loadData() {
  const res = await fetch(`${API_URL}/cases`);
  cases = await res.json();
  render(); renderStats();
}

// Skapa nytt ärende (ersätter delar av addCase())
async function createCase(payload) {
  const res = await fetch(`${API_URL}/cases`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

// Uppdatera ärende (ersätter saveUpdate())
async function updateCase(id, payload) {
  const res = await fetch(`${API_URL}/cases/${id}`, {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  });
  return res.json();
}

// Ta bort ärende (ersätter deleteCase())
async function deleteCase(id) {
  await fetch(`${API_URL}/cases/${id}`, { method: 'DELETE' });
}

// Exportera (ersätter exportCSV() — öppnar nu bara länken till backend)
function exportCSV() {
  window.open(`${API_URL}/export/csv`, '_blank');
}
```

Jag bygger om hela frontend-filen åt dig när du är redo för det steget — säg
till så kopplar jag ihop alla knappar (addCase, saveUpdate, deleteCase,
render, m.fl.) mot dessa nya API-anrop, så att designen förblir identisk men
all data går via Python-backend istället för `localStorage`.

## Filöversikt

| Fil                  | Ansvar                                                          |
|-----------------------|------------------------------------------------------------------|
| `main.py`              | FastAPI-app, alla REST-endpoints                                 |
| `models.py`            | Pydantic-modeller (fältnamn matchar frontend exakt)               |
| `db.py`                | All Supabase-kommunikation (CRUD)                                |
| `external_source.py`   | Hämtar/normaliserar data från din externa källa (fyll i när redo) |
| `exporter.py`          | Skriver xlsx/csv-filer                                            |
| `scheduler.py`         | Dagligt schema: import 06:00, export 23:00                        |
