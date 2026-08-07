"""Ponto isolado para configurar e chamar o runtime CPLEX."""

from typing import Any

from architecture_example.instrumentation import log_execution_time


class CVRPSolver:
    """Encapsula a resolução e a política de falha do runtime CPLEX."""

    def __init__(self, model: Any):
        self.model = model

    @log_execution_time
    def solve(self) -> Any:
        """Resolve o modelo e retorna a solução encontrada."""
        solution = self.model.solve(log_output=True)
        if solution is None:
            raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
        return solution
