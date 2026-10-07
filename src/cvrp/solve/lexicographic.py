"""Execuções sucessivas das FOs, mantendo o modelo e o incumbente da FO1."""

from dataclasses import replace
from pathlib import Path
from time import perf_counter

from cvrp.config import PipelineConfig
from cvrp.domain.instance import InstanceData
from cvrp.domain.results import Diagnostic, ModelSolution, StageResult
from cvrp.model import CVRPBuilderCplex, CVRPBuilderDocplex


def remaining(deadline: float | None) -> float:
    return float("inf") if deadline is None else max(0.0, deadline - perf_counter())


class LexicographicSolver:
    def __init__(self, data: InstanceData, config: PipelineConfig) -> None:
        self.config = config
        self.builder = CVRPBuilderCplex(data, config) if config.backend == "cplex" else CVRPBuilderDocplex(data, config)
        self.cost_limit: float | None = None
        self.build_seconds = 0.0
        self.stages: list[StageResult] = []
        self.diagnostics: list[Diagnostic] = []

    def run(self, split_id: str, deadline: float | None = None, artifacts: Path | None = None) -> ModelSolution | None:
        started = perf_counter()
        self.builder.build()
        self.build_seconds = perf_counter() - started
        if self.config.export_lp and artifacts is not None:
            self.builder.export(artifacts / "fo1.lp")
        solve_deadline = perf_counter() + self.config.solve_seconds
        deadline = solve_deadline if deadline is None else min(deadline, solve_deadline)
        budget = min(self.config.solve_seconds * self.config.first_objective_fraction, remaining(deadline))
        first = self._stage("cost", budget, split_id)
        if first is None:
            return None
        self.cost_limit = first.cost + self.config.cost_slack(first.cost)
        second = self._refine(split_id, deadline, artifacts)
        if second is None or not self._preserves_priorities(first, second):
            self.diagnostics.append(Diagnostic("fo2_fallback", "Mantida solução da FO1", split_id=split_id))
            return first
        return second

    def _refine(self, split_id: str, deadline: float, artifacts: Path | None) -> ModelSolution | None:
        assert self.cost_limit is not None
        try:
            self.builder.freeze_cost(self.cost_limit)
            self.builder.minimize_balance()
            if self.config.export_lp and artifacts is not None:
                self.builder.export(artifacts / "fo2.lp")
            return self._stage("balance", remaining(deadline), split_id)
        except Exception as exc:
            self.stages.append(StageResult(split_id, "balance", "failed", None, None, None, 0, False))
            self.diagnostics.append(Diagnostic("fo2_failed", f"{type(exc).__name__}: {exc}", split_id=split_id))
            return None

    def _preserves_priorities(self, first: ModelSolution, second: ModelSolution) -> bool:
        assert self.cost_limit is not None
        if second.cost > self.cost_limit + 1e-7:
            return False
        slack = self.config.cost_slack(first.cost)
        return second.cost < first.cost - slack or second.balance <= first.balance + 1e-7

    def _stage(self, objective: str, budget: float, split_id: str) -> ModelSolution | None:
        if budget <= 0:
            self.stages.append(StageResult(split_id, objective, "budget_exhausted", None, None, None, 0, False))
            return None
        stage, chosen = self.builder.solve_stage(objective, budget, split_id)
        self.stages.append(stage)
        if chosen is not None:
            self.stages[-1] = replace(stage, cost=chosen.cost, balance=chosen.balance)
        return chosen

    def close(self) -> None:
        self.builder.close()
