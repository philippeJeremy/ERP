"""Tâches de fond du module catalog (exécutées par le worker, voir app/core/jobs.py)."""

from app.core.jobs import job
from app.modules.catalog import importer

job("catalog.analyze_import")(importer.analyze_job)
job("catalog.apply_import")(importer.apply_job)
