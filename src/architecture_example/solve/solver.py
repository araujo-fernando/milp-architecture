"""Ponto isolado para configurar e chamar o runtime CPLEX."""

from typing import Any

from architecture_example.instrumentation import log_execution_time


class CVRPSolver:
    """Encapsula a resolução e a política de falha do runtime CPLEX."""

    def __init__(self, model: Any, *, cplex_log: bool = False):
        self.model = model
        self.cplex_log = cplex_log

    @log_execution_time
    def solve(self) -> Any:
        """Resolve o modelo e retorna a solução encontrada."""
        solution = self.model.solve(log_output=self.cplex_log)
        if solution is None:
            raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
        return solution
