"""Tâches de fond du module mailing."""

from app.core.jobs import job
from app.modules.mailing import service

job("mailing.send")(service.send_job)
