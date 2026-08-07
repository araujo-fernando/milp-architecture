"""Contrato interno da instância concreta do problema."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Vehicle:
    identifier: str
    kind: str
    capacity_kg: float
    capacity_m3: float
    cost_per_km: float


@dataclass(frozen=True, slots=True)
class InstanceData:
    depot: str
    delivery_date: str
    nodes: tuple[str, ...]
    vehicles: tuple[Vehicle, ...]
    demand_kg: dict[int, float]
    demand_m3: dict[int, float]
    orders: dict[int, tuple[str, ...]]
    names: dict[int, str]
    distance: dict[tuple[int, int], float]
    cost: dict[tuple[int, int, int], float]
    valid_ijk: frozenset[tuple[int, int, int]]
    fixed_vehicle_cost: float
    currency: str
    discarded: tuple[dict[str, str], ...]
