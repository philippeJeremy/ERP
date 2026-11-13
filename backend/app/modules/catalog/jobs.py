"""Tâches de fond du module catalog (exécutées par le worker, voir app/core/jobs.py)."""

from app.core.jobs import job
from app.modules.catalog import importer

job("catalog.analyze_import")(importer.analyze_job)
job("catalog.apply_import")(importer.apply_job)

from app.modules.catalog import poller  # noqa: E402

job("catalog.poll_source")(poller.poll_source)
job("catalog.poll_due_sources")(poller.poll_due_sources)
