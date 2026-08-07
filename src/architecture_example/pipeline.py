"""Orquestra Transform → Build → Solve → Extract."""

import logging
from time import perf_counter
from typing import Any

from .instrumentation import log_execution_time
from .model import CVRPBuilder
from .report import SolutionReporter
from .solve import CVRPSolver
from .transform import InstanceTransformer

logger = logging.getLogger("architecture_example")


class CVRPPipeline:
    """Coordena o fluxo completo da instância até o JSON de solução."""

    def __init__(self, raw: dict[str, Any], cd: str, delivery_date: str | None = None, *, cplex_log: bool = False):
        self.transformer = InstanceTransformer(raw, cd, delivery_date)
        self.cplex_log = cplex_log

    @log_execution_time
    def run(self) -> dict[str, Any]:
        """Executa Transform → Build → Solve → Extract."""
        data = self.transformer.transform()
        builder = CVRPBuilder(data)
        started = perf_counter()
        builder.build()
        built = perf_counter()
        logger.info(
            "Modelo construído com %d variáveis e %d restrições",
            builder.model.number_of_variables,
            builder.model.number_of_constraints,
        )
        solution = CVRPSolver(builder.model, cplex_log=self.cplex_log).solve()
        return SolutionReporter(data, builder, solution, built - started, perf_counter() - built).extract()
