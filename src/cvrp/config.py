"""Configuração explícita dos orçamentos e das etapas do pipeline."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal

type Backend = Literal["docplex", "cplex"]
type DistanceMode = Literal["complete_with_geography", "provided_only"]


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    backend: Backend = "docplex"
    clusters: int = 4
    seed: int = 42
    parallel: bool = False
    workers: int = 2
    solver_threads: int = 1
    cpu_budget: int = 4
    memory_budget_mb: int = 4096
    solver_work_memory_mb: float = 256.0
    solve_seconds: float = 30.0
    first_objective_fraction: float = 0.7
    mip_gap: float = 0.01
    absolute_tolerance: float = 1e-6
    relative_tolerance: float = 0.0
    postprocess_seconds: float = 5.0
    postprocess_candidates: int = 10_000
    total_seconds: float | None = None
    distance_mode: DistanceMode = "complete_with_geography"
    cplex_log: bool = False
    export_lp: bool = False
    output_dir: Path | None = None

    def __post_init__(self) -> None:
        self._validate_choices()
        self._validate_numbers()
        active_workers = self.workers if self.parallel else 1
        if active_workers * self.solver_threads > self.cpu_budget:
            raise ValueError("workers * solver_threads excede cpu_budget")
        if self.export_lp and self.output_dir is None:
            raise ValueError("export_lp requer output_dir")

    def _validate_choices(self) -> None:
        if self.backend not in {"docplex", "cplex"}:
            raise ValueError(f"Builder desconhecido: {self.backend}")
        if self.distance_mode not in {"complete_with_geography", "provided_only"}:
            raise ValueError("distance_mode inválido")
        if not 0 < self.first_objective_fraction < 1:
            raise ValueError("first_objective_fraction deve estar entre 0 e 1")
        if not 0 <= self.mip_gap <= 1:
            raise ValueError("mip_gap deve estar entre 0 e 1")
        if type(self.seed) is not int or not 0 <= self.seed <= 2_100_000_000:
            raise ValueError("seed deve ser inteiro entre 0 e 2100000000")

    def _validate_numbers(self) -> None:
        counts = (
            self.clusters,
            self.workers,
            self.solver_threads,
            self.cpu_budget,
            self.memory_budget_mb,
            self.postprocess_candidates,
        )
        if any(type(value) is not int or value < 1 for value in counts):
            raise ValueError("Contagens da configuração devem ser inteiros positivos")
        positive: tuple[float, ...] = (self.solve_seconds, self.solver_work_memory_mb)
        if self.total_seconds is not None:
            positive += (self.total_seconds,)
        nonnegative = (self.postprocess_seconds, self.absolute_tolerance, self.relative_tolerance)
        if any(not isfinite(value) or value <= 0 for value in positive):
            raise ValueError("Orçamentos devem ser finitos e positivos")
        if any(not isfinite(value) or value < 0 for value in nonnegative):
            raise ValueError("Tolerâncias e orçamento de pós devem ser finitos e não negativos")

    def cost_slack(self, value: float) -> float:
        return self.absolute_tolerance + self.relative_tolerance * abs(value)
