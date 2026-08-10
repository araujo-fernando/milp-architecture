"""Façade genérica de modelagem linear sobre o runtime CPLEX."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cplex import Cplex

from architecture_example.instrumentation import Instrumentation as inst

type SparseExpression = list[Sequence[int] | Sequence[float]]
type SparseRow = tuple[SparseExpression, str, float]


@dataclass(frozen=True)
class LinearConstraint:
    """Uma restrição linear esparsa representada por índices de variáveis."""

    indices: Sequence[int]
    coefficients: Sequence[float]
    sense: str
    rhs: float


@dataclass(frozen=True)
class Solution:
    """Resultado independente da API de solução do CPLEX."""

    status: str
    objective_value: float
    values: tuple[float, ...]

    def value(self, variable: int) -> float:
        """Retorna o valor da variável pelo seu índice."""
        return self.values[variable]


class Solver:
    """Cria e resolve modelos lineares inteiros sem expor objetos CPLEX."""

    _ROW_BATCH_SIZE = 2_000

    def __init__(self, *, problem_name: str, cplex_log: bool = False):
        self._model = Cplex()
        self._model.set_problem_name(problem_name)
        self.cplex_log = cplex_log

    @property
    def variable_count(self) -> int:
        return self._model.variables.get_num()

    @property
    def constraint_count(self) -> int:
        return self._model.linear_constraints.get_num()

    def add_binary_variables(self, objective_coefficients: Sequence[float]) -> tuple[int, ...]:
        """Adiciona variáveis binárias e retorna seus índices estáveis."""
        first_index = self.variable_count
        count = len(objective_coefficients)
        self._model.variables.add(
            obj=objective_coefficients,
            lb=[0.0] * count,
            ub=[1.0] * count,
            types="B" * count,
        )
        return tuple(range(first_index, first_index + count))

    def minimize(self) -> None:
        """Define a minimização dos coeficientes informados ao criar variáveis."""
        self._model.objective.set_sense(self._model.objective.sense.minimize)

    def add_linear_constraints(self, rows: Iterable[LinearConstraint]) -> None:
        """Adiciona objetos de restrição; compatibilidade para consumidores externos."""
        self.add_sparse_rows(([row.indices, row.coefficients], row.sense, row.rhs) for row in rows)

    def add_sparse_rows(self, rows: Iterable[SparseRow]) -> None:
        """Envia linhas esparsas cruas em lotes, sem objetos por restrição."""
        expressions: list[SparseExpression] = []
        senses: list[str] = []
        rhs: list[float] = []
        add = self._model.linear_constraints.add
        batch_size = self._ROW_BATCH_SIZE
        append_expression = expressions.append
        append_sense = senses.append
        append_rhs = rhs.append

        for expression, sense, bound in rows:
            append_expression(expression)
            append_sense(sense)
            append_rhs(bound)
            if len(expressions) == batch_size:
                add(lin_expr=expressions, senses="".join(senses), rhs=rhs)
                expressions, senses, rhs = [], [], []
                append_expression = expressions.append
                append_sense = senses.append
                append_rhs = rhs.append
        if expressions:
            add(lin_expr=expressions, senses="".join(senses), rhs=rhs)



    @inst.log_execution_time
    def solve(self) -> Solution:
        """Resolve o modelo e materializa um resultado independente do runtime."""
        if not self.cplex_log:
            self._model.set_log_stream(None)
            self._model.set_results_stream(None)
            self._model.set_warning_stream(None)
            self._model.set_error_stream(None)
        self._model.solve()
        if not self._model.solution.is_primal_feasible():
            raise RuntimeError("Solver não encontrou solução; configure um runtime CPLEX compatível")
        return Solution(
            status=self._model.solution.get_status_string(),
            objective_value=self._model.solution.get_objective_value(),
            values=tuple(self._model.solution.get_values()),
        )
