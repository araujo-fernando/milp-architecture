"""Resolve um split no processo local ou em processos isolados."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path

from cvrp.config import PipelineConfig
from cvrp.domain.instance import ProblemData, ProblemSplit
from cvrp.domain.results import Diagnostic, SplitResult
from cvrp.instrumentation import Instrumentation
from cvrp.report.routes import extract_routes
from cvrp.transform.build_instance import materialize
from cvrp.validation.solution import SolutionValidator

from .lexicographic import LexicographicSolver, remaining


def solve_split(
    problem: ProblemData, split: ProblemSplit, config: PipelineConfig, deadline: float | None = None, run_id: str = ""
) -> SplitResult:
    if remaining(deadline) <= 0:
        return _failure(split, "budget_exhausted", "Orçamento esgotado antes da construção")
    if estimated_memory_mb(split) > config.memory_budget_mb:
        return _failure(split, "failed", "Estimativa de memória do split excede memory_budget_mb")
    artifacts = _artifacts(config, run_id, split.identifier)
    data = materialize(problem, split)
    runner = LexicographicSolver(data, config)
    try:
        chosen = runner.run(split.identifier, deadline, artifacts)
        routes = () if chosen is None else extract_routes(data, chosen)
        if chosen is not None:
            SolutionValidator().validate(
                problem,
                routes,
                expected_customers=split.customer_ids,
                allowed_vehicles=tuple(v.identifier for v in split.vehicles),
                cost_limit=runner.cost_limit,
            )
        result = SplitResult(
            split.identifier,
            routes,
            tuple(runner.stages),
            "feasible" if chosen is not None else "no_incumbent",
            runner.build_seconds,
            runner.builder.variable_count,
            runner.builder.constraint_count,
            runner.builder.nonzero_count,
            runner.cost_limit,
            tuple(runner.diagnostics),
            split.customer_ids,
            tuple(v.identifier for v in split.vehicles),
        )
    finally:
        runner.close()
    return result


def _artifacts(config: PipelineConfig, run_id: str, split_id: str) -> Path | None:
    if config.output_dir is None:
        return None
    path = config.output_dir / "work" / run_id / split_id
    path.mkdir(parents=True, exist_ok=True)
    Instrumentation.configure(path / "execution.log", force=True)
    return path


def _failure(split: ProblemSplit, status: str, message: str) -> SplitResult:
    diagnostic = Diagnostic(status, message, split_id=split.identifier, level="ERROR")
    return SplitResult(
        split.identifier,
        (),
        (),
        status,
        diagnostics=(diagnostic,),
        customer_ids=split.customer_ids,
        vehicle_ids=tuple(v.identifier for v in split.vehicles),
    )


def estimated_memory_mb(split: ProblemSplit) -> float:
    """Estimativa conservadora para scheduling, não um limite de RSS do solver."""
    n, k = len(split.customer_ids), len(split.vehicles)
    arcs = n * (n + 1) * k
    variables = arcs + (n + 1) * k + n + 2
    return 64.0 + (variables * 400 + arcs * 300) / 1_048_576


class SplitExecutor:
    def run(
        self,
        problem: ProblemData,
        splits: tuple[ProblemSplit, ...],
        config: PipelineConfig,
        deadline: float | None = None,
        run_id: str = "",
    ) -> tuple[SplitResult, ...]:
        if config.parallel and len(splits) > 1:
            return self._parallel(problem, splits, config, deadline, run_id)
        return tuple(self._safe_solve(problem, split, config, deadline, run_id) for split in splits)

    @staticmethod
    def _safe_solve(
        problem: ProblemData, split: ProblemSplit, config: PipelineConfig, deadline: float | None, run_id: str
    ) -> SplitResult:
        try:
            return solve_split(problem, split, config, deadline, run_id)
        except Exception as exc:
            return _failure(split, "failed", f"{type(exc).__name__}: {exc}")

    def _parallel(
        self,
        problem: ProblemData,
        splits: tuple[ProblemSplit, ...],
        config: PipelineConfig,
        deadline: float | None,
        run_id: str,
    ) -> tuple[SplitResult, ...]:
        results: list[SplitResult] = []
        largest = max(estimated_memory_mb(split) for split in splits)
        workers = min(config.workers, len(splits), max(1, int(config.memory_budget_mb // largest)))
        try:
            self._collect_parallel(problem, splits, config, deadline, run_id, workers, results)
        except Exception as exc:
            completed = {result.split_id for result in results}
            results.extend(
                _failure(split, "failed", f"{type(exc).__name__}: {exc}")
                for split in splits
                if split.identifier not in completed
            )
        if workers < min(config.workers, len(splits)):
            warning = Diagnostic(
                "workers_por_memoria", f"Paralelismo reduzido para {workers} pela estimativa de memória"
            )
            results = [replace(item, diagnostics=(*item.diagnostics, warning)) for item in results]
        return tuple(sorted(results, key=lambda result: result.split_id))

    @staticmethod
    def _collect_parallel(
        problem: ProblemData,
        splits: tuple[ProblemSplit, ...],
        config: PipelineConfig,
        deadline: float | None,
        run_id: str,
        workers: int,
        results: list[SplitResult],
    ) -> None:
        with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
            futures = {}
            for split in splits:
                try:
                    futures[pool.submit(solve_split, problem, split, config, deadline, run_id)] = split
                except Exception as exc:
                    results.append(_failure(split, "failed", f"{type(exc).__name__}: {exc}"))
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(_failure(futures[future], "failed", f"{type(exc).__name__}: {exc}"))


def unpartitioned_fallback(
    problem: ProblemData, config: PipelineConfig, deadline: float | None, run_id: str
) -> tuple[SplitResult, ...]:
    split = ProblemSplit("fallback-001", tuple(problem.customers), problem.vehicles)
    result = SplitExecutor().run(problem, (split,), config, deadline, run_id)
    warning = Diagnostic(
        "partition_fallback", "Partição não resolveu todos os clientes; tentativa global", level="WARN"
    )
    return tuple(replace(item, diagnostics=(warning, *item.diagnostics)) for item in result)
