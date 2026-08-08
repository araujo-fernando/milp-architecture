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
        self.x = self.model.binary_var_dict(self.data.valid_ijk, name=None)
        indices = [(i, k) for i in range(len(self.data.nodes)) for k in range(len(self.data.vehicles))]
        self.y = self.model.binary_var_dict(indices, name=None)
        with inst.measure("restrições do modelo"):
            self._add_constraints()
        variable_cost = self.model.sum(self.data.cost[key] * variable for key, variable in self.x.items())
        fixed_cost = self.data.fixed_vehicle_cost * self.model.sum(self.y[0, k] for k in range(len(self.data.vehicles)))
        self.model.minimize(variable_cost + fixed_cost)
        return self.model

    def _add_constraints(self) -> None:
        data, model = self.data, self.model
        vehicles = range(len(data.vehicles))
        nodes = range(len(data.nodes))

        with inst.measure("R1"):
            model.add_constraints(model.sum(self.y[i, k] for k in vehicles) == 1 for i in data.demand_kg)
        
        with inst.measure("R2"):
            model.add_constraint(model.sum(self.y[0, k] for k in vehicles) <= len(data.vehicles))
        
        with inst.measure("R3"):
            model.add_constraints(model.sum(self.x[i, j, k] for j in nodes if (i, j, k) in self.x) == self.y[i, k] for i in nodes for k in vehicles)
        
        with inst.measure("R4"):
            model.add_constraints(model.sum(self.x[i, j, k] for i in nodes if (i, j, k) in self.x) == self.y[j, k] for j in nodes for k in vehicles)
        
        with inst.measure("R5"):
            model.add_constraints(model.sum(data.demand_kg[i] * self.y[i, k] for i in data.demand_kg) <= data.vehicles[k].capacity_kg for k in vehicles)
        
        with inst.measure("R6"):
            model.add_constraints(model.sum(data.demand_m3[i] * self.y[i, k] for i in data.demand_m3) <= data.vehicles[k].capacity_m3 for k in vehicles)
        
        with inst.measure("R7"):
            model.add_constraints(
            model.sum(self.x[i, j, k] for i in subset for j in subset if (i, j, k) in self.x) <= len(subset) - 1
            for size in range(2, len(data.demand_kg) + 1)
            for subset in combinations(data.demand_kg, size)
            for k in vehicles
        )
