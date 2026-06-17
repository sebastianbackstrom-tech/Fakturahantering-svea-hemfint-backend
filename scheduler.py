"""
scheduler.py — Kör det dagliga jobbet automatiskt:
  - 06:00  importera från extern källa (fetch_external_data -> Supabase)
  - 23:00  exportera databasen till .xlsx och .csv

Tiderna är exempel — ändra i CRON_IMPORT_HOUR / CRON_EXPORT_HOUR.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler

import db
import exporter
from external_source import fetch_external_data

logger = logging.getLogger("fakturahantering.scheduler")

CRON_IMPORT_HOUR = 6   # 06:00 varje dag
CRON_EXPORT_HOUR = 23  # 23:00 varje dag

_scheduler = BackgroundScheduler()


def daily_import_job():
    logger.info("Startar dagligt importjobb...")
    try:
        rows = fetch_external_data()
        result = db.bulk_upsert_from_external(rows)
        logger.info(f"Import klar: {result}")
    except Exception as e:
        logger.error(f"Importjobb misslyckades: {e}")


def daily_export_job():
    logger.info("Startar dagligt exportjobb...")
    try:
        cases = db.list_cases()
        xlsx_path = exporter.export_to_xlsx(cases)
        csv_path = exporter.export_to_csv(cases)
        logger.info(f"Export klar: {xlsx_path}, {csv_path}")
    except Exception as e:
        logger.error(f"Exportjobb misslyckades: {e}")


def start_scheduler():
    if _scheduler.running:
        return
    _scheduler.add_job(daily_import_job, "cron", hour=CRON_IMPORT_HOUR, minute=0)
    _scheduler.add_job(daily_export_job, "cron", hour=CRON_EXPORT_HOUR, minute=0)
    _scheduler.start()
    logger.info(
        f"Schemaläggare startad: import kl {CRON_IMPORT_HOUR}:00, "
        f"export kl {CRON_EXPORT_HOUR}:00"
    )
