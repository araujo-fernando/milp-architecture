"""Condições necessárias de viabilidade e integridade dos índices."""

from math import isfinite

from cvrp.domain.instance import Customer, InstanceData, ProblemData, Vehicle
from cvrp.io.reader import InputError


def fits(customer: Customer, vehicle: Vehicle, tolerance: float = 1e-7) -> bool:
    return (
        customer.demand_kg <= vehicle.capacity_kg + tolerance and customer.demand_m3 <= vehicle.capacity_m3 + tolerance
    )


def eligible(problem: ProblemData, customer: Customer, vehicle: Vehicle) -> bool:
    depot, client = problem.depot.identifier, customer.identifier
    return (
        fits(customer, vehicle)
        and problem.travel.allows(depot, client, vehicle)
        and problem.travel.allows(client, depot, vehicle)
    )


class ProblemValidator:
    def validate(self, problem: ProblemData) -> None:
        if not problem.customers:
            return
        if not problem.vehicles:
            raise InputError(f"Nenhum veículo disponível para {problem.depot.identifier}")
        if any(not isfinite(v.cost_per_km) for v in problem.vehicles):
            raise InputError("Custo agregado de veículo não finito")
        if any(not isfinite(c.demand_kg) or not isfinite(c.demand_m3) for c in problem.customers.values()):
            raise InputError("Demanda agregada não finita")
        for customer in problem.customers.values():
            if not any(fits(customer, vehicle) for vehicle in problem.vehicles):
                raise InputError(f"Demanda excede capacidade conjunta: {customer.identifier}")
            if not any(eligible(problem, customer, vehicle) for vehicle in problem.vehicles):
                raise InputError(f"Cliente sem veículo elegível com ida e retorno: {customer.identifier}")
        self._total_capacity(problem)

    @staticmethod
    def _total_capacity(problem: ProblemData) -> None:
        if sum(c.demand_kg for c in problem.customers.values()) > sum(v.capacity_kg for v in problem.vehicles) + 1e-7:
            raise InputError("Capacidade total em kg insuficiente")
        if sum(c.demand_m3 for c in problem.customers.values()) > sum(v.capacity_m3 for v in problem.vehicles) + 1e-7:
            raise InputError("Capacidade total em m³ insuficiente")


class InstanceValidator:
    def validate(self, data: InstanceData) -> None:
        if len(set(data.nodes)) != len(data.nodes) or data.nodes[0] != data.depot:
            raise InputError("Índices de nós inconsistentes")
        if len({v.identifier for v in data.vehicles}) != len(data.vehicles):
            raise InputError("IDs de veículos duplicados")
        for i, customer in data.customers.items():
            if not any(
                self._reachable(data, i, k) and fits(customer, vehicle) for k, vehicle in enumerate(data.vehicles)
            ):
                raise InputError(f"Split sem capacidade/ida/retorno: {customer.identifier}")
        if any(not isfinite(value) or value < 0 for value in data.cost.values()):
            raise InputError("Custo inválido na instância")
        if set(data.cost) != set(data.valid_ijk):
            raise InputError("Índices de custos e arcos divergem")

    @staticmethod
    def _reachable(data: InstanceData, i: int, k: int) -> bool:
        return i in data.outgoing.get((0, k), ()) and 0 in data.outgoing.get((i, k), ())
