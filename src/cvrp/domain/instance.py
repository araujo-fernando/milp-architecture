"""Dados de negócio canônicos e instância matemática esparsa."""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from cvrp.config import DistanceMode

from .results import Diagnostic


@dataclass(frozen=True, slots=True)
class Location:
    identifier: str
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class Customer:
    location: Location
    demand_kg: float
    demand_m3: float
    orders: tuple[str, ...]

    @property
    def identifier(self) -> str:
        return self.location.identifier


@dataclass(frozen=True, slots=True)
class Vehicle:
    identifier: str
    kind: str
    capacity_kg: float
    capacity_m3: float
    cost_per_km: float


@dataclass(frozen=True, slots=True)
class TravelData:
    locations: dict[str, Location]
    overrides: dict[tuple[str, str], float]
    blocked: dict[str, frozenset[str]]
    mode: DistanceMode = "complete_with_geography"

    def allows(self, origin: str, destination: str, vehicle: Vehicle) -> bool:
        blocked = self.blocked.get(vehicle.kind, frozenset())
        permitted = origin != destination and origin not in blocked and destination not in blocked
        return permitted and (self.mode != "provided_only" or (origin, destination) in self.overrides)

    def distance(self, origin: str, destination: str) -> float:
        key = (origin, destination)
        if key in self.overrides:
            return self.overrides[key]
        if self.mode == "provided_only":
            raise ValueError(f"Arco ausente: {origin} → {destination}")
        return haversine(self.locations[origin], self.locations[destination])


def haversine(origin: Location, destination: Location) -> float:
    lat1, lon1 = radians(origin.latitude), radians(origin.longitude)
    lat2, lon2 = radians(destination.latitude), radians(destination.longitude)
    value = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(min(1.0, max(0.0, value))))


@dataclass(frozen=True, slots=True)
class ProblemData:
    depot: Location
    delivery_date: str
    customers: dict[str, Customer]
    vehicles: tuple[Vehicle, ...]
    travel: TravelData
    fixed_vehicle_cost: float
    currency: str
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class InstanceData:
    depot: str
    delivery_date: str
    nodes: tuple[str, ...]
    vehicles: tuple[Vehicle, ...]
    customers: dict[int, Customer]
    distance: dict[tuple[int, int], float]
    cost: dict[tuple[int, int, int], float]
    valid_ijk: tuple[tuple[int, int, int], ...]
    outgoing: dict[tuple[int, int], tuple[int, ...]]
    incoming: dict[tuple[int, int], tuple[int, ...]]
    fixed_vehicle_cost: float
    currency: str
    diagnostics: tuple[Diagnostic, ...] = ()

    @property
    def demand_kg(self) -> dict[int, float]:
        return {i: customer.demand_kg for i, customer in self.customers.items()}

    @property
    def demand_m3(self) -> dict[int, float]:
        return {i: customer.demand_m3 for i, customer in self.customers.items()}

    @property
    def discarded(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {"codigo": d.entity, "motivo": d.code}
            for d in self.diagnostics
            if d.code in {"coordenada_ausente", "cliente_nao_cadastrado"}
        )


@dataclass(frozen=True, slots=True)
class ProblemSplit:
    identifier: str
    customer_ids: tuple[str, ...]
    vehicles: tuple[Vehicle, ...]
