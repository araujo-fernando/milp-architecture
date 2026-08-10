"""API enxuta para criar e resolver modelos binários lineares com CPLEX.

O fluxo usual é criar um :class:`Solver`, adicionar as variáveis binárias,
definir a minimização, acrescentar as restrições e chamar :meth:`Solver.solve`.
Os índices devolvidos por :meth:`Solver.add_binary_variables` identificam as
variáveis tanto nas restrições quanto no :meth:`Solution.value` retornado.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from cplex import Cplex

from cvrp.instrumentation import Instrumentation as inst

type SparseExpression = list[Sequence[int] | Sequence[float]]
type SparseRow = tuple[SparseExpression, str, float]


@dataclass(frozen=True)
class LinearConstraint:
    """Representa uma restrição linear esparsa.

    ``indices`` e ``coefficients`` formam os termos da expressão na mesma
    posição: ``sum(coefficients[i] * x[indices[i]])``. ``sense`` deve ser
    ``"L"`` (menor ou igual), ``"E"`` (igual) ou ``"G"`` (maior ou igual),
    e ``rhs`` é o lado direito. Por exemplo,
    ``LinearConstraint([x, y], [2.0, 1.0], "L", 5.0)`` representa
    ``2*x + y <= 5``.

    Use esta classe com :meth:`Solver.add_linear_constraints`. Para evitar a
    criação de um objeto por linha em modelos grandes, use
    :meth:`Solver.add_sparse_rows` diretamente.
    """

    indices: Sequence[int]
    coefficients: Sequence[float]
    sense: str
    rhs: float


@dataclass(frozen=True)
class Solution:
    """Resultado materializado, sem dependência da API do CPLEX.

    Attributes:
        status: Texto de status retornado pelo CPLEX.
        objective_value: Valor da função objetivo da solução encontrada.
        values: Valores das variáveis, ordenados por seus índices de criação.
    """

    status: str
    objective_value: float
    values: tuple[float, ...]

    def value(self, variable: int) -> float:
        """Retorna o valor da variável identificada por ``variable``.

        Passe um índice devolvido por :meth:`Solver.add_binary_variables`.
        Por exemplo, ``solution.value(x)`` consulta a variável ``x``. Um
        índice inexistente produz ``IndexError``.
        """
        return self.values[variable]


class Solver:
    """Cria e resolve modelos lineares binários sem expor objetos CPLEX.

    Exemplo mínimo::

        solver = Solver(problem_name="exemplo")
        (x,) = solver.add_binary_variables([2.0])
        solver.minimize()
        solver.add_linear_constraints([
            LinearConstraint([x], [1.0], "G", 1.0),
        ])
        solution = solver.solve()
        assert solution.value(x) == 1.0

    Os coeficientes da função objetivo são informados ao criar as variáveis;
    as restrições aceitam os índices dessas variáveis. Há métodos específicos
    para variáveis binárias, inteiras e contínuas.
    """

    _ROW_BATCH_SIZE = 2_000

    def __init__(self, *, problem_name: str, cplex_log: bool = False):
        """Inicializa um modelo vazio.

        Args:
            problem_name: Nome atribuído ao modelo no CPLEX, útil para logs e
                diagnósticos.
            cplex_log: Se ``True``, preserva a saída do CPLEX durante
                :meth:`solve`; se ``False`` (padrão), silencia seus streams.
        """
        self._model = Cplex()
        self._model.set_problem_name(problem_name)
        self.cplex_log = cplex_log

    @property
    def variable_count(self) -> int:
        """Quantidade atual de variáveis criadas no modelo."""
        return self._model.variables.get_num()

    @property
    def constraint_count(self) -> int:
        """Quantidade atual de restrições lineares adicionadas ao modelo."""
        return self._model.linear_constraints.get_num()

    def add_binary_variables(
        self,
        objective_coefficients: Sequence[float],
        lower_bounds: Sequence[float] | None = None,
        upper_bounds: Sequence[float] | None = None,
    ) -> tuple[int, ...]:
        """Adiciona variáveis binárias e devolve seus índices estáveis.

        Args:
            objective_coefficients: Um coeficiente da função objetivo por
                variável. A sequência ``[2.0, 3.0]`` cria ``x0`` e ``x1`` com
                objetivo ``2*x0 + 3*x1``.
            lower_bounds: Limite inferior de cada variável, na mesma ordem
                dos coeficientes. O padrão é zero.
            upper_bounds: Limite superior de cada variável, na mesma ordem
                dos coeficientes. O padrão é um.

        Returns:
            Tupla de índices na mesma ordem dos coeficientes. Guarde-os para
            montar restrições e consultar a solução. As variáveis têm domínio
            ``{0, 1}``.

        Raises:
            ValueError: Se uma sequência de limites não tiver um valor para
                cada coeficiente.

        Os limites explícitos devem ser compatíveis com o domínio binário,
        isto é, estar entre zero e um.
        """
        return self._add_variables(
            objective_coefficients,
            lower_bounds,
            upper_bounds,
            variable_type="B",
            default_lower_bound=0.0,
            default_upper_bound=1.0,
        )

    def add_integer_variables(
        self,
        objective_coefficients: Sequence[float],
        lower_bounds: Sequence[float] | None = None,
        upper_bounds: Sequence[float] | None = None,
    ) -> tuple[int, ...]:
        """Adiciona variáveis inteiras com os limites informados.

        Args:
            objective_coefficients: Um coeficiente da função objetivo por
                variável.
            lower_bounds: Limite inferior de cada variável. Sem valor
                informado, todas começam em zero.
            upper_bounds: Limite superior de cada variável. Sem valor
                informado, não há limite superior finito.

        Returns:
            Índices das variáveis, na ordem dos coeficientes. Por exemplo,
            ``add_integer_variables([1.0], [-2.0], [3.0])`` cria uma variável
            inteira entre ``-2`` e ``3``.

        Raises:
            ValueError: Se uma sequência de limites não tiver um valor para
                cada coeficiente.
        """
        return self._add_variables(
            objective_coefficients,
            lower_bounds,
            upper_bounds,
            variable_type="I",
            default_lower_bound=0.0,
            default_upper_bound=float("inf"),
        )

    def add_continuous_variables(
        self,
        objective_coefficients: Sequence[float],
        lower_bounds: Sequence[float] | None = None,
        upper_bounds: Sequence[float] | None = None,
    ) -> tuple[int, ...]:
        """Adiciona variáveis contínuas com os limites informados.

        Args:
            objective_coefficients: Um coeficiente da função objetivo por
                variável.
            lower_bounds: Limite inferior de cada variável. Sem valor
                informado, todas começam em zero.
            upper_bounds: Limite superior de cada variável. Sem valor
                informado, não há limite superior finito.

        Returns:
            Índices das variáveis, na ordem dos coeficientes. Por exemplo,
            ``add_continuous_variables([1.0], [-2.0], [3.0])`` cria uma
            variável contínua entre ``-2`` e ``3``.

        Raises:
            ValueError: Se uma sequência de limites não tiver um valor para
                cada coeficiente.
        """
        return self._add_variables(
            objective_coefficients,
            lower_bounds,
            upper_bounds,
            variable_type="C",
            default_lower_bound=0.0,
            default_upper_bound=float("inf"),
        )

    def minimize(self) -> None:
        """Define que a função objetivo deve ser minimizada.

        Chame este método depois de criar as variáveis e antes de
        :meth:`solve`. A função objetivo é formada pelos coeficientes passados
        a :meth:`add_binary_variables`.
        """
        self._model.objective.set_sense(self._model.objective.sense.minimize)

    def add_linear_constraints(self, rows: Iterable[LinearConstraint]) -> None:
        """Adiciona restrições descritas por :class:`LinearConstraint`.

        Args:
            rows: Iterável de restrições. Cada uma referencia variáveis pelos
                índices devolvidos por :meth:`add_binary_variables`.

        Esta é a interface mais legível. Para grandes volumes, prefira
        :meth:`add_sparse_rows`, que evita instanciar ``LinearConstraint``.
        """
        self.add_sparse_rows(([row.indices, row.coefficients], row.sense, row.rhs) for row in rows)

    def add_sparse_rows(self, rows: Iterable[SparseRow]) -> None:
        """Adiciona restrições esparsas cruas, em lotes eficientes.

        Args:
            rows: Iterável de tuplas ``([indices, coefficients], sense, rhs)``.
                ``indices`` e ``coefficients`` devem ter o mesmo tamanho e
                representar ``sum(coefficient * x[index])``. ``sense`` é
                ``"L"`` para ``<=``, ``"E"`` para ``==`` ou ``"G"`` para
                ``>=``. Exemplo: ``([ [x, y], [2.0, 1.0] ], "L", 5.0)``
                adiciona ``2*x + y <= 5``.

        Os índices devem ter sido retornados por
        :meth:`add_binary_variables`. O iterável pode ser um gerador; suas
        linhas são enviadas ao CPLEX em lotes de até ``2_000``.
        """
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
        """Resolve o modelo e devolve uma solução materializada.

        Returns:
            :class:`Solution` com status, valor objetivo e valores indexados
            das variáveis. Consulte uma variável com ``solution.value(x)``,
            em que ``x`` foi devolvido por :meth:`add_binary_variables`.

        Raises:
            RuntimeError: Se o CPLEX terminar sem uma solução primal viável.

        A saída do CPLEX só é exibida quando o construtor recebeu
        ``cplex_log=True``.
        """
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

    def _add_variables(
        self,
        objective_coefficients: Sequence[float],
        lower_bounds: Sequence[float] | None,
        upper_bounds: Sequence[float] | None,
        *,
        variable_type: str,
        default_lower_bound: float,
        default_upper_bound: float,
    ) -> tuple[int, ...]:
        """Adiciona uma família homogênea de variáveis ao modelo CPLEX."""
        count = len(objective_coefficients)
        lower_bounds = self._resolve_bounds(lower_bounds, count, default_lower_bound, "lower_bounds")
        upper_bounds = self._resolve_bounds(upper_bounds, count, default_upper_bound, "upper_bounds")
        first_index = self.variable_count
        self._model.variables.add(
            obj=objective_coefficients,
            lb=lower_bounds,
            ub=upper_bounds,
            types=variable_type * count,
        )
        return tuple(range(first_index, first_index + count))

    @staticmethod
    def _resolve_bounds(
        bounds: Sequence[float] | None,
        count: int,
        default: float,
        argument_name: str,
    ) -> Sequence[float]:
        """Normaliza limites opcionais e garante sua cardinalidade."""
        if bounds is None:
            return [default] * count
        if len(bounds) != count:
            raise ValueError(f"{argument_name} deve ter {count} valores; recebeu {len(bounds)}")
        return bounds
