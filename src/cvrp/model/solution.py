"""Métricas das decisões escolhidas, independentes da FO ativa."""

from collections import Counter
from math import isfinite

from cvrp.domain.instance import InstanceData
from cvrp.domain.results import ModelSolution


def finite_metric(value: float | None) -> float | None:
    """Converte sentinelas de infinito do solver em ausência de métrica."""
    return value if value is not None and isfinite(value) and abs(value) < 1e20 else None


def stop_bounds(arcs: tuple[tuple[int, int, int], ...]) -> tuple[float, float]:
    """Extremos reais das paradas nas rotas utilizadas, para normalizar L/U."""
    counts = Counter(k for _, j, k in arcs if j != 0)
    return float(min(counts.values(), default=0)), float(max(counts.values(), default=0))


def describe_arcs(data: InstanceData, arcs: tuple[tuple[int, int, int], ...]) -> ModelSolution:
    stops = Counter(k for _, j, k in arcs if j != 0)
    used = {k for i, _, k in arcs if i == 0}
    cost = sum(data.cost[key] for key in arcs) + len(used) * data.fixed_vehicle_cost
    balance = max(stops.values(), default=0) - min(stops.values(), default=0)
    return ModelSolution(arcs, cost, float(balance))
