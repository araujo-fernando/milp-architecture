"""Builder Docplex da formulação vehicle-flow de três índices."""

from itertools import combinations
from typing import Any

from docplex.mp.model import Model

from architecture_example.domain import InstanceData
from architecture_example.instrumentation import Instrumentation as inst


class CVRPBuilder:
    """Constrói a formulação vehicle-flow da seção 3, com cortes DFJ."""

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
