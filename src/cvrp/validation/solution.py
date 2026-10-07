"""Auditoria independente das rotas e recálculo dos objetivos de negócio."""

from math import isfinite

from cvrp.domain.instance import ProblemData
from cvrp.domain.results import Route, RouteMetrics

CAPACITY_TOLERANCE = 1e-7


class SolutionError(ValueError):
    """Uma solução concreta viola um contrato de negócio."""


def route_metrics(problem: ProblemData, route: Route) -> RouteMetrics:
    vehicle = next((v for v in problem.vehicles if v.identifier == route.vehicle_id), None)
    if vehicle is None:
        raise SolutionError(f"Veículo desconhecido: {route.vehicle_id}")
    if any(client not in problem.customers for client in route.customers):
        raise SolutionError("Rota contém cliente desconhecido")
    nodes = (problem.depot.identifier, *route.customers, problem.depot.identifier)
    distance = (
        sum(problem.travel.distance(a, b) for a, b in zip(nodes, nodes[1:], strict=False)) if route.customers else 0.0
    )
    return RouteMetrics(
        distance_km=distance,
        load_kg=sum(problem.customers[c].demand_kg for c in route.customers),
        load_m3=sum(problem.customers[c].demand_m3 for c in route.customers),
        fixed_cost=problem.fixed_vehicle_cost if route.customers else 0.0,
        variable_cost=distance * vehicle.cost_per_km,
        stops=len(route.customers),
    )


def objective_vector(problem: ProblemData, routes: tuple[Route, ...]) -> tuple[float, float]:
    metrics = tuple(route_metrics(problem, route) for route in routes)
    stops = tuple(metric.stops for metric in metrics if metric.stops)
    balance = float(max(stops) - min(stops)) if stops else 0.0
    return sum(metric.total_cost for metric in metrics), balance


class SolutionValidator:
    def validate(
        self,
        problem: ProblemData,
        routes: tuple[Route, ...],
        expected_customers: tuple[str, ...] | None = None,
        allowed_vehicles: tuple[str, ...] | None = None,
        cost_limit: float | None = None,
    ) -> None:
        expected = tuple(problem.customers) if expected_customers is None else expected_customers
        allowed = tuple(v.identifier for v in problem.vehicles) if allowed_vehicles is None else allowed_vehicles
        clients = tuple(c for route in routes for c in route.customers)
        vehicles = tuple(route.vehicle_id for route in routes)
        self._check_membership(clients, expected, vehicles, allowed)
        for route in routes:
            self._check_route(problem, route)
        cost, balance = objective_vector(problem, routes)
        if not isfinite(cost) or not isfinite(balance):
            raise SolutionError("Objetivos não finitos")
        if cost_limit is not None and (not isfinite(cost_limit) or cost > cost_limit + CAPACITY_TOLERANCE):
            raise SolutionError("Limite lexicográfico de custo excedido")

    @staticmethod
    def _check_membership(
        clients: tuple[str, ...], expected: tuple[str, ...], vehicles: tuple[str, ...], allowed: tuple[str, ...]
    ) -> None:
        if len(clients) != len(set(clients)) or set(clients) != set(expected):
            raise SolutionError("Atendimento deve cobrir cada cliente esperado exatamente uma vez")
        if len(vehicles) != len(set(vehicles)):
            raise SolutionError("Veículo físico utilizado em mais de uma rota")
        if not set(vehicles).issubset(allowed):
            raise SolutionError("Veículo fora da frota autorizada")

    @staticmethod
    def _check_route(problem: ProblemData, route: Route) -> None:
        vehicle = next((v for v in problem.vehicles if v.identifier == route.vehicle_id), None)
        if vehicle is None or not route.customers:
            raise SolutionError("Rota vazia ou veículo desconhecido")
        nodes = (problem.depot.identifier, *route.customers, problem.depot.identifier)
        if any(not problem.travel.allows(a, b, vehicle) for a, b in zip(nodes, nodes[1:], strict=False)):
            raise SolutionError("Rota usa arco ou circulação proibidos")
        metric = route_metrics(problem, route)
        values = (metric.distance_km, metric.load_kg, metric.load_m3, metric.fixed_cost, metric.variable_cost)
        if any(not isfinite(value) or value < 0 for value in values):
            raise SolutionError("Métricas de rota inválidas")
        if metric.load_kg > vehicle.capacity_kg + CAPACITY_TOLERANCE:
            raise SolutionError("Capacidade em kg excedida")
        if metric.load_m3 > vehicle.capacity_m3 + CAPACITY_TOLERANCE:
            raise SolutionError("Capacidade em m³ excedida")
