"""Orquestra Transform → Build → Solve → Extract."""

from typing import Any

from .instrumentation import Instrumentation as inst
from .model import CVRPBuilder
from .report import SolutionReporter
from .solve import CVRPSolver
from .transform import InstanceTransformer


class CVRPPipeline:
    """Coordena o fluxo completo da instância até o JSON de solução."""

    def __init__(self, raw: dict[str, Any], cd: str, delivery_date: str | None = None, *, cplex_log: bool = False):
        self.transformer = InstanceTransformer(raw, cd, delivery_date)
        self.cplex_log = cplex_log

    @inst.log_execution_time
    def run(self) -> dict[str, Any]:
        """Executa Transform → Build → Solve → Extract."""
        data = self.transformer.transform()
        builder = CVRPBuilder(data)
        with inst.measure("construção do modelo") as build_measurement:
            builder.build()
        inst.info(
            "Modelo construído com %d variáveis e %d restrições",
            builder.model.number_of_variables,
            builder.model.number_of_constraints,
        )
        with inst.measure("resolução do modelo") as solve_measurement:
            solution = CVRPSolver(builder.model, cplex_log=self.cplex_log).solve()
        return SolutionReporter(data, builder, solution, build_measurement.elapsed_seconds, solve_measurement.elapsed_seconds).extract()
