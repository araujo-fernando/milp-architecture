"""Contratos dos campos operacionais utilizados pelo template."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Place:
    code: str
    name: str
    depot_code: str
    active: bool
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True, slots=True)
class Product:
    sku: str
    weight_kg: float
    volume_m3: float


@dataclass(frozen=True, slots=True)
class OrderItem:
    sku: str
    boxes: int


@dataclass(frozen=True, slots=True)
class Order:
    number: str
    customer_code: str
    status: str
    delivery_date: str
    items: tuple[OrderItem, ...]


@dataclass(frozen=True, slots=True)
class VehicleKind:
    code: str
    capacity_kg: float
    capacity_m3: float
    relative_cost: float


@dataclass(frozen=True, slots=True)
class Availability:
    depot_code: str
    kind: str
    quantity: int
    maintenance: int


@dataclass(frozen=True, slots=True)
class CirculationRule:
    depot_code: str
    vehicle_kind: str
    customer_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DistanceOverride:
    origin: str
    destination: str
    distance_km: float


@dataclass(frozen=True, slots=True)
class RawScenario:
    reference_date: str
    currency: str
    cost_per_km: float
    fixed_vehicle_cost: float
    depots: tuple[Place, ...]
    clients: tuple[Place, ...]
    products: tuple[Product, ...]
    orders: tuple[Order, ...]
    vehicle_kinds: tuple[VehicleKind, ...]
    availability: tuple[Availability, ...]
    circulation: tuple[CirculationRule, ...]
    distances: tuple[DistanceOverride, ...]
