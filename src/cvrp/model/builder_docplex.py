"""Formulação CVRP diretamente na API algébrica do Docplex."""

from pathlib import Path
from time import perf_counter

from docplex.mp.dvar import Var
from docplex.mp.model import Model
from docplex.mp.solution import SolveSolution

from cvrp.config import PipelineConfig
from cvrp.domain.instance import InstanceData
from cvrp.domain.results import ModelSolution, StageResult

from .solution import describe_arcs, finite_metric, stop_bounds


class CVRPBuilderDocplex:
    def __init__(self, data: InstanceData, config: PipelineConfig | None = None) -> None:
        self.data = data
        self.config = config or PipelineConfig()
        self.model = Model(name="cvrp", checker="numeric")
        self.x: dict[tuple[int, int, int], Var] = {}
        self.y: dict[tuple[int, int], Var] = {}
        self.u: dict[int, Var] = {}
        self.incumbent: SolveSolution | None = None

    def build(self) -> Model:
        d, m = self.data, self.model
        self.x = m.binary_var_dict(d.valid_ijk, name=lambda key: "x_" + "_".join(map(str, key)))
        self.y = m.binary_var_dict(
            ((i, k) for i in range(len(d.nodes)) for k in range(len(d.vehicles))),
            name=lambda key: f"y_{key[0]}_{key[1]}",
        )
        self.u = m.continuous_var_dict(d.customers, lb=1, ub=len(d.customers), name="u")
        self.lower = m.continuous_var(lb=0, ub=len(d.customers), name="L")
        self.upper = m.continuous_var(lb=0, ub=len(d.customers), name="U")
        self.cost_expression = m.sum(d.cost[key] * var for key, var in self.x.items()) + d.fixed_vehicle_cost * m.sum(
            self.y[0, k] for k in range(len(d.vehicles))
        )
        self._assignment_and_flow()
        self._capacities()
        self._connectivity()
        self._balance()
        m.minimize(self.cost_expression)
        m.parameters.threads = self.config.solver_threads
        m.parameters.randomseed = self.config.seed
        m.parameters.mip.tolerances.mipgap = self.config.mip_gap
        m.parameters.workmem = self.config.solver_work_memory_mb
        m.parameters.mip.strategy.file = 3
        return m

    def _assignment_and_flow(self) -> None:
        d, m, x, y = self.data, self.model, self.x, self.y
        I, K, V = tuple(d.customers), range(len(d.vehicles)), range(len(d.nodes))
        m.add_constraints((m.sum(y[i, k] for k in K) == 1 for i in I), names=(f"r1_{i}" for i in I))
        m.add_constraints(
            (m.sum(x[i, j, k] for j in d.outgoing.get((i, k), ())) == y[i, k] for i in V for k in K),
            names=(f"r3_{i}_{k}" for i in V for k in K),
        )
        m.add_constraints(
            (m.sum(x[i, j, k] for i in d.incoming.get((j, k), ())) == y[j, k] for j in V for k in K),
            names=(f"r4_{j}_{k}" for j in V for k in K),
        )

    def _capacities(self) -> None:
        d, m, y = self.data, self.model, self.y
        I, K = tuple(d.customers), range(len(d.vehicles))
        m.add_constraints(
            (m.sum(d.customers[i].demand_kg * y[i, k] for i in I) <= d.vehicles[k].capacity_kg for k in K),
            names=(f"r5_{k}" for k in K),
        )
        m.add_constraints(
            (m.sum(d.customers[i].demand_m3 * y[i, k] for i in I) <= d.vehicles[k].capacity_m3 for k in K),
            names=(f"r6_{k}" for k in K),
        )

    def _connectivity(self) -> None:
        n = len(self.data.customers)
        keys = tuple((i, j, k) for i, j, k in self.data.valid_ijk if i and j)
        self.model.add_constraints(
            (self.u[i] - self.u[j] + n * self.x[i, j, k] <= n - 1 for i, j, k in keys),
            names=(f"r7_{i}_{j}_{k}" for i, j, k in keys),
        )

    def _balance(self) -> None:
        d, m, y = self.data, self.model, self.y
        I, K, n = tuple(d.customers), range(len(d.vehicles)), len(d.customers)
        stops = {k: m.sum(y[i, k] for i in I) for k in K}
        m.add_constraints((stops[k] <= self.upper for k in K), names=(f"r8_{k}" for k in K))
        m.add_constraints((stops[k] >= self.lower - n * (1 - y[0, k]) for k in K), names=(f"r9_{k}" for k in K))
        m.add_constraints((stops[k] <= n * y[0, k] for k in K), names=(f"r10_{k}" for k in K))
        m.add_constraint(self.lower <= self.upper, ctname="r11")

    def freeze_cost(self, limit: float) -> None:
        self.model.add_constraint(self.cost_expression <= limit, ctname="lex_cost_limit")

    def minimize_balance(self) -> None:
        self.model.minimize(self.upper - self.lower)
        if self.incumbent is not None and (self.x or self.y):
            self.model.add_mip_start(self.incumbent, complete_vars=True)

    def solve_stage(self, objective: str, seconds: float, split_id: str) -> tuple[StageResult, ModelSolution | None]:
        self.model.parameters.timelimit = seconds
        started = perf_counter()
        solution = self.model.solve(log_output=self.config.cplex_log)
        elapsed = perf_counter() - started
        details = self.model.solve_details
        chosen = None
        if solution is not None:
            self.incumbent = solution
            arcs = tuple(key for key, var in self.x.items() if solution.get_value(var) > 0.5)
            chosen = describe_arcs(self.data, arcs)
            lower, upper = stop_bounds(arcs)
            self.incumbent.add_var_value(self.lower, lower)
            self.incumbent.add_var_value(self.upper, upper)
        stage = StageResult(
            split_id,
            objective,
            details.status,
            None if solution is None else solution.objective_value,
            finite_metric(details.best_bound) if self.x or self.y else None,
            finite_metric(details.mip_relative_gap) if solution is not None and (self.x or self.y) else None,
            elapsed,
            solution is not None,
            details.status_code in {1, 101},
            None if chosen is None else chosen.cost,
            None if chosen is None else chosen.balance,
        )
        return stage, chosen

    @property
    def variable_count(self) -> int:
        return self.model.number_of_variables

    @property
    def constraint_count(self) -> int:
        return self.model.number_of_constraints

    @property
    def nonzero_count(self) -> int:
        return self.model.get_cplex().linear_constraints.get_num_nonzeros()

    def export(self, path: Path) -> None:
        self.model.export_as_lp(str(path))

    def close(self) -> None:
        self.model.end()
