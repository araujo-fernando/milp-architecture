"""Ponto isolado para configurar e chamar o runtime CPLEX."""

from typing import Any

from cplex import Cplex

from architecture_example.instrumentation import Instrumentation as inst


class CVRPSolver:
    """Encapsula a resolução e a política de falha do runtime CPLEX."""

    def __init__(self, model: Any, *, cplex_log: bool = False):
        self.model = model
        self.cplex_log = cplex_log

    @inst.log_execution_time
    def solve(self) -> Any:
        """Resolve o modelo e retorna a solução encontrada."""
        if isinstance(self.model, Cplex):
            if not self.cplex_log:
                self.model.set_log_stream(None)
                self.model.set_results_stream(None)
                self.model.set_warning_stream(None)
                self.model.set_error_stream(None)
            self.model.solve()
            if not self.model.solution.is_primal_feasible():
                raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
            return self.model
        solution = self.model.solve(log_output=self.cplex_log)
        if solution is None:
            raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
        return solution
