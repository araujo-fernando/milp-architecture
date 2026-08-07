"""Orquestra Transform → Build → Solve → Extract."""

from time import perf_counter
from typing import Any

from .model import CVRPBuilder
from .report import SolutionReporter
from .solve import CVRPSolver
from .transform import InstanceTransformer


class CVRPPipeline:
    """Coordena o fluxo completo da instância até o JSON de solução."""

    def __init__(self, raw: dict[str, Any], cd: str, delivery_date: str | None = None):
        self.transformer = InstanceTransformer(raw, cd, delivery_date)

    def run(self) -> dict[str, Any]:
        """Executa Transform → Build → Solve → Extract."""
        started = perf_counter()
        data = self.transformer.transform()
        builder = CVRPBuilder(data)
        builder.build()
        built = perf_counter()
        solution = CVRPSolver(builder.model).solve()
        return SolutionReporter(data, builder, solution, built - started, perf_counter() - built).extract()
