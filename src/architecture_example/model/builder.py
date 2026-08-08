"""Builders da formulação vehicle-flow de três índices."""

from collections.abc import Iterable
from itertools import combinations
from typing import Any

from cplex import Cplex, SparsePair
from docplex.mp.model import Model

from architecture_example.domain import InstanceData
from architecture_example.instrumentation import Instrumentation as inst


class CVRPBuilderDocplex:
    """Constrói a formulação vehicle-flow com a camada de modelagem Docplex."""

    def __init__(self, data: InstanceData):
        self.data = data
        self.model = Model(name="cvrp", ignore_names=True, checker="off")
        self.x: dict[tuple[int, int, int], Any] = {}
        self.y: dict[tuple[int, int], Any] = {}

    @inst.log_execution_time
    def build(self) -> Model:
        data, model = self.data, self.model
        valid_ijk = data.valid_ijk
        node_count = len(data.nodes)
        vehicle_count = len(data.vehicles)

        self.x = model.binary_var_dict(valid_ijk, name=None)
        indices = [(i, k) for i in range(node_count) for k in range(vehicle_count)]
        self.y = model.binary_var_dict(indices, name=None)
        with inst.measure("restrições do modelo"):
            self._add_constraints()
        cost = data.cost
        fixed_vehicle_cost = data.fixed_vehicle_cost
        variable_cost = model.sum(cost[key] * variable for key, variable in self.x.items())
        fixed_cost = fixed_vehicle_cost * model.sum(self.y[0, k] for k in range(vehicle_count))
        model.minimize(variable_cost + fixed_cost)
        return model

    def _add_constraints(self) -> None:
        data, model = self.data, self.model
        demand_kg = data.demand_kg
        demand_m3 = data.demand_m3

        vehicles_capacity_kg = {k: vehicle.capacity_kg for k, vehicle in enumerate(data.vehicles)}
        vehicles_capacity_m3 = {k: vehicle.capacity_m3 for k, vehicle in enumerate(data.vehicles)}

        vehicle_count = len(vehicles_capacity_kg)
        node_count = len(data.nodes)
        customer_count = len(demand_kg)
        vehicles = range(vehicle_count)
        nodes = range(node_count)

        y = self.y
        x = self.x
        msum = model.sum

        with inst.measure("R1"):
            model.add_constraints(msum(y[i, k] for k in vehicles) == 1 for i in demand_kg)

        with inst.measure("R2"):
            model.add_constraint(msum(y[0, k] for k in vehicles) <= vehicle_count)

        with inst.measure("R3"):
            model.add_constraints(
                msum(x[i, j, k] for j in nodes if (i, j, k) in x) == y[i, k] for i in nodes for k in vehicles
            )

        with inst.measure("R4"):
            model.add_constraints(
                msum(x[i, j, k] for i in nodes if (i, j, k) in x) == y[j, k] for j in nodes for k in vehicles
            )

        with inst.measure("R5"):
            model.add_constraints(
                msum(demand_kg[i] * y[i, k] for i in demand_kg) <= vehicles_capacity_kg[k] for k in vehicles
            )

        with inst.measure("R6"):
            model.add_constraints(
                msum(demand_m3[i] * y[i, k] for i in demand_m3) <= vehicles_capacity_m3[k] for k in vehicles
            )

        with inst.measure("R7"):
            model.add_constraints(
                msum(x[i, j, k] for i in subset for j in subset if (i, j, k) in x) <= size - 1
                for size in range(2, customer_count + 1)
                for subset in combinations(demand_kg, size)
                for k in vehicles
            )


class CVRPBuilderCplex:
    """Constrói a mesma formulação diretamente pela API Python do CPLEX."""

    _ROW_BATCH_SIZE = 2_000

    def __init__(self, data: InstanceData):
        self.data = data
        self.model = Cplex()
        self.model.set_problem_name("cvrp")
        self.x: dict[tuple[int, int, int], int] = {}
        self.y: dict[tuple[int, int], int] = {}

    @inst.log_execution_time
    def build(self) -> Cplex:
        data, model = self.data, self.model
        valid_ijk = data.valid_ijk
        node_count = len(data.nodes)
        vehicle_count = len(data.vehicles)

        # Agrupa os arcos por veículo. Além de tornar a ordem determinística,
        # isso permite reutilizar os índices de R7 entre veículos completos.
        x_keys = tuple(sorted(valid_ijk, key=lambda key: (key[2], key[0], key[1])))
        y_keys = tuple((i, k) for i in range(node_count) for k in range(vehicle_count))
        self.x = {key: index for index, key in enumerate(x_keys)}
        self.y = {key: len(x_keys) + index for index, key in enumerate(y_keys)}

        objective = [data.cost[key] for key in x_keys] + [data.fixed_vehicle_cost if i == 0 else 0.0 for i, _ in y_keys]
        variable_count = len(objective)
        model.variables.add(
            obj=objective,
            lb=[0.0] * variable_count,
            ub=[1.0] * variable_count,
            types="B" * variable_count,
        )
        model.objective.set_sense(model.objective.sense.minimize)

        with inst.measure("restrições do modelo"):
            self._add_constraints()
        return model

    def _add_constraints(self) -> None:
        data = self.data
        demand_kg = data.demand_kg
        demand_m3 = data.demand_m3
        vehicles_capacity_kg = {k: vehicle.capacity_kg for k, vehicle in enumerate(data.vehicles)}
        vehicles_capacity_m3 = {k: vehicle.capacity_m3 for k, vehicle in enumerate(data.vehicles)}
        vehicle_count = len(vehicles_capacity_kg)
        node_count = len(data.nodes)
        customer_count = len(demand_kg)
        vehicles = range(vehicle_count)
        nodes = range(node_count)
        x, y = self.x, self.y
        arc_indices = [[[-1] * node_count for _ in nodes] for _ in vehicles]
        for (i, j, k), index in x.items():
            arc_indices[k][i][j] = index

        with inst.measure("R1"):
            self._add_rows(
                (SparsePair(ind=[y[i, k] for k in vehicles], val=[1.0] * vehicle_count), "E", 1.0) for i in demand_kg
            )

        with inst.measure("R2"):
            self._add_rows(
                ((SparsePair(ind=[y[0, k] for k in vehicles], val=[1.0] * vehicle_count), "L", float(vehicle_count)),)
            )

        with inst.measure("R3"):
            self._add_rows(
                (
                    SparsePair(
                        ind=indices + [y[i, k]],
                        val=[1.0] * len(indices) + [-1.0],
                    ),
                    "E",
                    0.0,
                )
                for i in nodes
                for k in vehicles
                for indices in ([index for index in arc_indices[k][i] if index >= 0],)
            )

        with inst.measure("R4"):
            self._add_rows(
                (
                    SparsePair(
                        ind=indices + [y[j, k]],
                        val=[1.0] * len(indices) + [-1.0],
                    ),
                    "E",
                    0.0,
                )
                for j in nodes
                for k in vehicles
                for indices in ([arc_indices[k][i][j] for i in nodes if arc_indices[k][i][j] >= 0],)
            )

        with inst.measure("R5"):
            self._add_rows(
                (
                    SparsePair(ind=[y[i, k] for i in demand_kg], val=list(demand_kg.values())),
                    "L",
                    vehicles_capacity_kg[k],
                )
                for k in vehicles
            )

        with inst.measure("R6"):
            self._add_rows(
                (
                    SparsePair(ind=[y[i, k] for i in demand_m3], val=list(demand_m3.values())),
                    "L",
                    vehicles_capacity_m3[k],
                )
                for k in vehicles
            )

        with inst.measure("R7"):
            customer_nodes = tuple(demand_kg)
            dense_customer_arcs = all(
                arc_indices[k][i][j] >= 0 for k in vehicles for i in customer_nodes for j in customer_nodes if i != j
            )
            complete_vehicle_arcs = vehicle_count * node_count * (node_count - 1) == len(x)
            if dense_customer_arcs and complete_vehicle_arcs:
                base_matrix = arc_indices[0]
                arcs_per_vehicle = len(x) // vehicle_count
                rows = (
                    ([indices, [1.0] * len(indices)], "L", float(size - 1))
                    for size in range(2, customer_count + 1)
                    for subset in combinations(customer_nodes, size)
                    for base_indices in ([base_matrix[i][j] for i in subset for j in subset if i != j],)
                    for vehicle_offset in range(0, len(x), arcs_per_vehicle)
                    for indices in (base_indices if vehicle_offset == 0 else [index + vehicle_offset for index in base_indices],)
                )
            else:
                rows = (
                    ([indices, [1.0] * len(indices)], "L", float(size - 1))
                    for size in range(2, customer_count + 1)
                    for subset in combinations(customer_nodes, size)
                    for k in vehicles
                    for matrix in (arc_indices[k],)
                    for indices in ([matrix[i][j] for i in subset for j in subset if matrix[i][j] >= 0],)
                )
            self._add_rows(rows)

    def _add_rows(self, rows: Iterable[tuple[Any, str, float]]) -> None:
        """Envia restrições ao CPLEX em lotes para limitar o uso de memória."""
        expressions: list[Any] = []
        senses: list[str] = []
        rhs: list[float] = []
        for expression, sense, bound in rows:
            expressions.append(expression)
            senses.append(sense)
            rhs.append(bound)
            if len(expressions) == self._ROW_BATCH_SIZE:
                self.model.linear_constraints.add(lin_expr=expressions, senses="".join(senses), rhs=rhs)
                expressions, senses, rhs = [], [], []
        if expressions:
            self.model.linear_constraints.add(lin_expr=expressions, senses="".join(senses), rhs=rhs)
