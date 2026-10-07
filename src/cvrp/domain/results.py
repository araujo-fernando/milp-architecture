"""Contratos serializáveis de solução, diagnósticos e medição."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    message: str
    entity: str = ""
    split_id: str = ""
    level: str = "WARN"


@dataclass(frozen=True, slots=True)
class Route:
    vehicle_id: str
    customers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RouteMetrics:
    distance_km: float
    load_kg: float
    load_m3: float
    fixed_cost: float
    variable_cost: float
    stops: int

    @property
    def total_cost(self) -> float:
        return self.fixed_cost + self.variable_cost


@dataclass(frozen=True, slots=True)
class StageResult:
    split_id: str
    objective: str
    status: str
    value: float | None
    bound: float | None
    gap: float | None
    seconds: float
    has_incumbent: bool
    proven_optimal: bool = False
    cost: float | None = None
    balance: float | None = None


@dataclass(frozen=True, slots=True)
class ModelSolution:
    arcs: tuple[tuple[int, int, int], ...]
    cost: float
    balance: float


@dataclass(frozen=True, slots=True)
class SplitResult:
    split_id: str
    routes: tuple[Route, ...]
    stages: tuple[StageResult, ...]
    status: str
    build_seconds: float = 0.0
    variable_count: int = 0
    constraint_count: int = 0
    nonzero_count: int = 0
    cost_limit: float | None = None
    diagnostics: tuple[Diagnostic, ...] = ()
    customer_ids: tuple[str, ...] = ()
    vehicle_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PostprocessResult:
    routes: tuple[Route, ...]
    cost_before: float
    cost_after: float
    balance_before: float
    balance_after: float
    seconds: float
    accepted_moves: int
    candidates: int
    stop_reason: str


@dataclass(frozen=True, slots=True)
class RoutingSolution:
    routes: tuple[Route, ...]
    splits: tuple[SplitResult, ...]
    status: str
    diagnostics: tuple[Diagnostic, ...] = ()
    postprocess: PostprocessResult | None = None
    timings: dict[str, float] = field(default_factory=dict)
    run_id: str = ""
    attempts: tuple[SplitResult, ...] = ()
