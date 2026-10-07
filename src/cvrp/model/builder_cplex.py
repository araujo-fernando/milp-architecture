"""Mesma formulação CVRP diretamente na API CPLEX, com linhas esparsas em lotes."""

from collections.abc import Iterable
from pathlib import Path
from time import perf_counter

from cplex import Cplex, SparsePair

from cvrp.config import PipelineConfig
from cvrp.domain.instance import InstanceData
from cvrp.domain.results import ModelSolution, StageResult

from .solution import describe_arcs, finite_metric, stop_bounds

type Row = tuple[str, list[int], list[float], str, float]


class CVRPBuilderCplex:
    def __init__(self, data: InstanceData, config: PipelineConfig | None = None, *, cplex_log: bool = False) -> None:
        self.data = data
        self.config = config or PipelineConfig(backend="cplex", cplex_log=cplex_log)
        self.model = Cplex()
        self.model.set_problem_name("cvrp")
        self.x: dict[tuple[int, int, int], int] = {}
        self.y: dict[tuple[int, int], int] = {}
        self.u: dict[int, int] = {}
        self.incumbent: list[float] | None = None
        if not self.config.cplex_log:
            self.model.set_log_stream(None)
            self.model.set_results_stream(None)
            self.model.set_warning_stream(None)
            self.model.set_error_stream(None)

    def build(self) -> Cplex:
        d, m = self.data, self.model
        x_keys = d.valid_ijk
        y_keys = tuple((i, k) for i in range(len(d.nodes)) for k in range(len(d.vehicles)))
        u_keys = tuple(d.customers)
        names = (
            [f"x_{i}_{j}_{k}" for i, j, k in x_keys]
            + [f"y_{i}_{k}" for i, k in y_keys]
            + [f"u_{i}" for i in u_keys]
            + ["L", "U"]
        )
        binary_count, n = len(x_keys) + len(y_keys), len(u_keys)
        self.cost_coefficients = (
            [d.cost[key] for key in x_keys]
            + [d.fixed_vehicle_cost if i == 0 else 0.0 for i, _ in y_keys]
            + [0.0] * (n + 2)
        )
        m.variables.add(
            obj=self.cost_coefficients,
            lb=[0.0] * binary_count + [1.0] * n + [0.0, 0.0],
            ub=[1.0] * binary_count + [float(n)] * (n + 2),
            types="B" * binary_count + "C" * (n + 2),
            names=names,
        )
        self.x = {key: i for i, key in enumerate(x_keys)}
        self.y = {key: len(x_keys) + i for i, key in enumerate(y_keys)}
        self.u = {key: binary_count + i for i, key in enumerate(u_keys)}
        self.lower, self.upper = binary_count + n, binary_count + n + 1
        m.objective.set_sense(m.objective.sense.minimize)
        self._assignment_and_flow()
        self._capacities()
        self._connectivity()
        self._balance()
        m.parameters.threads.set(self.config.solver_threads)
        m.parameters.randomseed.set(self.config.seed)
        m.parameters.mip.tolerances.mipgap.set(self.config.mip_gap)
        m.parameters.workmem.set(self.config.solver_work_memory_mb)
        m.parameters.mip.strategy.file.set(3)
        return m

    def _add_rows(self, rows: Iterable[Row]) -> None:
        batch: list[Row] = []
        for row in rows:
            batch.append(row)
            if len(batch) == 2000:
                self._flush(batch)
                batch.clear()
        if batch:
            self._flush(batch)

    def _flush(self, batch: list[Row]) -> None:
        self.model.linear_constraints.add(
            lin_expr=[SparsePair(ind=indices, val=coefficients) for _, indices, coefficients, _, _ in batch],
            senses="".join(sense for _, _, _, sense, _ in batch),
            rhs=[rhs for _, _, _, _, rhs in batch],
            names=[name for name, _, _, _, _ in batch],
        )

    def _assignment_and_flow(self) -> None:
        d, y, x = self.data, self.y, self.x
        I, K, V = tuple(d.customers), range(len(d.vehicles)), range(len(d.nodes))
        self._add_rows((f"r1_{i}", [y[i, k] for k in K], [1.0] * len(K), "E", 1.0) for i in I)
        self._add_rows(
            (
                f"r3_{i}_{k}",
                [x[i, j, k] for j in d.outgoing.get((i, k), ())] + [y[i, k]],
                [1.0] * len(d.outgoing.get((i, k), ())) + [-1.0],
                "E",
                0.0,
            )
            for i in V
            for k in K
        )
        self._add_rows(
            (
                f"r4_{j}_{k}",
                [x[i, j, k] for i in d.incoming.get((j, k), ())] + [y[j, k]],
                [1.0] * len(d.incoming.get((j, k), ())) + [-1.0],
                "E",
                0.0,
            )
            for j in V
            for k in K
        )

    def _capacities(self) -> None:
        d, y = self.data, self.y
        I, K = tuple(d.customers), range(len(d.vehicles))
        self._add_rows(
            (f"r5_{k}", [y[i, k] for i in I], [d.customers[i].demand_kg for i in I], "L", d.vehicles[k].capacity_kg)
            for k in K
        )
        self._add_rows(
            (f"r6_{k}", [y[i, k] for i in I], [d.customers[i].demand_m3 for i in I], "L", d.vehicles[k].capacity_m3)
            for k in K
        )

    def _connectivity(self) -> None:
        n = len(self.data.customers)
        self._add_rows(
            (f"r7_{i}_{j}_{k}", [self.u[i], self.u[j], self.x[i, j, k]], [1.0, -1.0, float(n)], "L", float(n - 1))
            for i, j, k in self.data.valid_ijk
            if i and j
        )

    def _balance(self) -> None:
        I, K, n = tuple(self.data.customers), range(len(self.data.vehicles)), len(self.data.customers)
        self._add_rows((f"r8_{k}", [self.y[i, k] for i in I] + [self.upper], [1.0] * n + [-1.0], "L", 0.0) for k in K)
        self._add_rows(
            (
                f"r9_{k}",
                [self.y[i, k] for i in I] + [self.lower, self.y[0, k]],
                [1.0] * n + [-1.0, -float(n)],
                "G",
                -float(n),
            )
            for k in K
        )
        self._add_rows(
            (f"r10_{k}", [self.y[i, k] for i in I] + [self.y[0, k]], [1.0] * n + [-float(n)], "L", 0.0) for k in K
        )
        self._add_rows((("r11", [self.lower, self.upper], [1.0, -1.0], "L", 0.0),))

    def freeze_cost(self, limit: float) -> None:
        terms = [(i, value) for i, value in enumerate(self.cost_coefficients) if value]
        self._add_rows((("lex_cost_limit", [i for i, _ in terms], [v for _, v in terms], "L", limit),))

    def minimize_balance(self) -> None:
        self.model.objective.set_linear((i, 0.0) for i in range(self.variable_count))
        self.model.objective.set_linear([(self.upper, 1.0), (self.lower, -1.0)])
        if self.incumbent is not None and (self.x or self.y):
            self.model.MIP_starts.add(
                SparsePair(ind=list(range(self.variable_count)), val=self.incumbent),
                self.model.MIP_starts.effort_level.auto,
            )

    def solve_stage(self, objective: str, seconds: float, split_id: str) -> tuple[StageResult, ModelSolution | None]:
        self.model.parameters.timelimit.set(seconds)
        started = perf_counter()
        self.model.solve()
        elapsed = perf_counter() - started
        solution = self.model.solution
        feasible = solution.is_primal_feasible()
        chosen = None
        if feasible:
            self.incumbent = solution.get_values()
            chosen = describe_arcs(self.data, tuple(key for key, i in self.x.items() if self.incumbent[i] > 0.5))
            self.incumbent[self.lower], self.incumbent[self.upper] = stop_bounds(chosen.arcs)
        stage = StageResult(
            split_id,
            objective,
            solution.get_status_string(),
            solution.get_objective_value() if feasible else None,
            finite_metric(solution.MIP.get_best_objective()) if self.x or self.y else None,
            finite_metric(solution.MIP.get_mip_relative_gap()) if feasible and (self.x or self.y) else None,
            elapsed,
            feasible,
            solution.get_status() in {1, 101},
            None if chosen is None else chosen.cost,
            None if chosen is None else chosen.balance,
        )
        return stage, chosen

    @property
    def variable_count(self) -> int:
        return self.model.variables.get_num()

    @property
    def constraint_count(self) -> int:
        return self.model.linear_constraints.get_num()

    @property
    def nonzero_count(self) -> int:
        return self.model.linear_constraints.get_num_nonzeros()

    def export(self, path: Path) -> None:
        self.model.write(str(path), filetype="lp")

    def close(self) -> None:
        self.model.end()
