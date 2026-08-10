"""Orquestra Transform → Build → Solve → Extract."""

from typing import Any, Literal

from .instrumentation import Instrumentation as inst
from .model import CVRPBuilderCplex, CVRPBuilderDocplex
from .report import SolutionReporter
from .transform import InstanceTransformer


class CVRPPipeline:
    """Coordena o fluxo completo da instância até o JSON de solução."""

    def __init__(self, raw: dict[str, Any], cd: str, delivery_date: str | None = None, *, builder: Literal["cplex", "docplex"] = "docplex", cplex_log: bool = False):
        if builder not in {"cplex", "docplex"}:
            raise ValueError(f"Builder desconhecido: {builder}")
        self.transformer = InstanceTransformer(raw, cd, delivery_date)
        self.builder = builder
        self.cplex_log = cplex_log

    @inst.log_execution_time
    def run(self) -> dict[str, Any]:
        """Executa Transform → Build → Solve → Extract."""
        data = self.transformer.transform()
        builder = CVRPBuilderCplex(data, cplex_log=self.cplex_log) if self.builder == "cplex" else CVRPBuilderDocplex(data)
        with inst.measure("construção do modelo") as build_measurement:
            builder.build()
        variable_count = builder.solver.variable_count if self.builder == "cplex" else builder.model.number_of_variables
        constraint_count = builder.solver.constraint_count if self.builder == "cplex" else builder.model.number_of_constraints
        inst.info(
            "Modelo construído com %d variáveis e %d restrições",
            variable_count,
            constraint_count,
        )
        with inst.measure("resolução do modelo") as solve_measurement:
            if self.builder == "cplex":
                solution = builder.solver.solve()
            else:
                solution = builder.model.solve(log_output=self.cplex_log)
                if solution is None:
                    raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
        return SolutionReporter(data, builder, solution, build_measurement.elapsed_seconds, solve_measurement.elapsed_seconds).extract()
