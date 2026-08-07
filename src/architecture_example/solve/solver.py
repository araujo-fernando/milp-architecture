"""Ponto isolado para configurar e chamar o runtime CPLEX."""

from typing import Any


class CVRPSolver:
    """Encapsula a resolução e a política de falha do runtime CPLEX."""

    def __init__(self, model: Any):
        self.model = model

    def solve(self) -> Any:
        """Resolve o modelo e retorna a solução encontrada."""
        solution = self.model.solve(log_output=False)
        if solution is None:
            raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
        return solution
