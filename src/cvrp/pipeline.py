"""Fluxo de dados explícito: preparar, dividir, resolver, validar, melhorar e reportar."""

from dataclasses import replace
from time import perf_counter

from .config import Backend, PipelineConfig
from .domain.instance import ProblemData
from .domain.results import Diagnostic, RoutingSolution, SplitResult
from .instrumentation import Instrumentation as inst
from .io.reader import InputError
from .postprocess import LocalSearch
from .preprocess import ClusterPreprocessor
from .report import ReportProjector, new_run_id
from .solve.executor import SplitExecutor, unpartitioned_fallback
from .solve.lexicographic import remaining
from .transform import InstanceTransformer
from .validation.solution import SolutionValidator


class CVRPPipeline:
    def __init__(
        self,
        raw: object,
        cd: str,
        delivery_date: str | None = None,
        *,
        builder: Backend | None = None,
        cplex_log: bool | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        self.config = config or PipelineConfig()
        if builder is not None:
            self.config = replace(self.config, backend=builder)
        if cplex_log is not None:
            self.config = replace(self.config, cplex_log=cplex_log)
        self.raw, self.cd, self.delivery_date = raw, cd, delivery_date
        self.problem: ProblemData | None = None
        self.solution: RoutingSolution | None = None

    @inst.log_execution_time
    def solve(self) -> RoutingSolution:
        self.problem = None
        self.solution = None
        started = perf_counter()
        run_id = new_run_id()
        reserve = 0 if self.config.total_seconds is None else min(1.0, self.config.total_seconds * 0.1)
        deadline = None if self.config.total_seconds is None else started + self.config.total_seconds - reserve
        timings: dict[str, float] = {}
        prepare_started = perf_counter()
        self.problem = InstanceTransformer(
            self.raw, self.cd, self.delivery_date, distance_mode=self.config.distance_mode
        ).prepare()
        timings["prepare"] = perf_counter() - prepare_started
        if not self.problem.customers:
            self.solution = RoutingSolution((), (), "empty", self.problem.diagnostics, timings=timings, run_id=run_id)
            return self.solution
        pre_started = perf_counter()
        preprocessor = ClusterPreprocessor()
        splits = preprocessor.split(self.problem, self.config)
        timings["preprocess"] = perf_counter() - pre_started
        solve_started = perf_counter()
        results = SplitExecutor().run(self.problem, splits, self.config, deadline, run_id)
        attempts: tuple[SplitResult, ...] = ()
        if len(splits) > 1 and any(result.status != "feasible" for result in results) and remaining(deadline) > 0:
            fallback = unpartitioned_fallback(self.problem, self.config, deadline, run_id)
            if all(result.status == "feasible" for result in fallback):
                attempts = results
                results = fallback
            else:
                attempts = fallback
        timings["solve_splits"] = perf_counter() - solve_started
        solution = self._consolidate(results, tuple(preprocessor.diagnostics), run_id, timings)
        solution = replace(solution, attempts=attempts)
        self.solution = self._postprocess(solution, deadline)
        timings["total_compute"] = perf_counter() - started
        self.solution = replace(self.solution, timings=timings)
        return self.solution

    def _consolidate(
        self,
        results: tuple[SplitResult, ...],
        diagnostics: tuple[Diagnostic, ...],
        run_id: str,
        timings: dict[str, float],
    ) -> RoutingSolution:
        assert self.problem is not None
        routes = tuple(route for result in results for route in result.routes)
        complete = all(result.status == "feasible" for result in results)
        status = "feasible" if complete else "partial" if routes else "no_incumbent"
        if results and all(result.status == "failed" for result in results):
            status = "failed"
        if complete:
            SolutionValidator().validate(self.problem, routes)
        issues = (*self.problem.diagnostics, *diagnostics, *(d for result in results for d in result.diagnostics))
        return RoutingSolution(routes, results, status, tuple(issues), timings=timings, run_id=run_id)

    def _postprocess(self, solution: RoutingSolution, deadline: float | None) -> RoutingSolution:
        assert self.problem is not None
        if solution.status != "feasible":
            return solution
        limits = tuple(result.cost_limit for result in solution.splits)
        cost_limit = sum(value for value in limits if value is not None)
        result = LocalSearch().improve(
            self.problem, solution.routes, self.config, deadline=deadline, cost_limit=cost_limit
        )
        SolutionValidator().validate(self.problem, result.routes, cost_limit=cost_limit)
        return replace(solution, routes=result.routes, postprocess=result)

    def run(self) -> dict[str, object]:
        try:
            solution = self.solve()
        except InputError as exc:
            self.solution = RoutingSolution(
                (), (), "invalid_input", (Diagnostic("invalid_input", str(exc), level="ERROR"),), run_id=new_run_id()
            )
            raise
        assert self.problem is not None
        return ReportProjector(self.problem, solution, self.config).output()
