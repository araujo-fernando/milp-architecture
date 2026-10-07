"""Projeções tipadas de relatórios independentes do solver."""

from .data import ReportData
from .projector import ReportProjector, new_run_id

__all__ = ["ReportData", "ReportProjector", "new_run_id"]
