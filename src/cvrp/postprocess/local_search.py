"""Relocate, swap e 2-opt direcionais com orçamento e teto de custo original."""

from collections.abc import Iterator
from time import perf_counter

from cvrp.config import PipelineConfig
from cvrp.domain.instance import ProblemData
from cvrp.domain.results import PostprocessResult, Route
from cvrp.validation.solution import SolutionError, SolutionValidator, objective_vector


class LocalSearch:
    def improve(
        self,
        problem: ProblemData,
        routes: tuple[Route, ...],
        config: PipelineConfig,
        deadline: float | None = None,
        cost_limit: float | None = None,
    ) -> PostprocessResult:
        start = perf_counter()
        validator = SolutionValidator()
        validator.validate(problem, routes, cost_limit=cost_limit)
        before = objective_vector(problem, routes)
        ceiling = before[0] + config.cost_slack(before[0])
        if cost_limit is not None:
            ceiling = min(ceiling, cost_limit)
        end = start + config.postprocess_seconds
        if deadline is not None:
            end = min(end, deadline)
        best, accepted, candidates, reason = self._search(problem, routes, config, end, ceiling)
        validator.validate(problem, best, cost_limit=ceiling)
        after = objective_vector(problem, best)
        return PostprocessResult(
            best, before[0], after[0], before[1], after[1], perf_counter() - start, accepted, candidates, reason
        )

    def _search(
        self, problem: ProblemData, routes: tuple[Route, ...], config: PipelineConfig, end: float, ceiling: float
    ) -> tuple[tuple[Route, ...], int, int, str]:
        accepted = candidates = 0
        best = routes
        best_cost_seen = objective_vector(problem, routes)[0]
        while perf_counter() < end:
            active_ceiling = min(ceiling, best_cost_seen + config.cost_slack(best_cost_seen))
            move, tested, reason = self._next_move(
                problem, best, config, end, active_ceiling, config.postprocess_candidates - candidates
            )
            candidates += tested
            if move is None:
                return best, accepted, candidates, reason
            best = move
            best_cost_seen = min(best_cost_seen, objective_vector(problem, best)[0])
            accepted += 1
        return best, accepted, candidates, "time_limit"

    def _next_move(
        self,
        problem: ProblemData,
        routes: tuple[Route, ...],
        config: PipelineConfig,
        end: float,
        ceiling: float,
        remaining: int,
    ) -> tuple[tuple[Route, ...] | None, int, str]:
        tested = 0
        original = objective_vector(problem, routes)
        for candidate in self._neighbors(problem, routes):
            if perf_counter() >= end:
                return None, tested, "time_limit"
            if tested >= remaining:
                return None, tested, "candidate_limit"
            tested += 1
            if self._acceptable(problem, candidate, original, config, ceiling):
                return candidate, tested, "improvement"
        return None, tested, "local_optimum"

    @staticmethod
    def _acceptable(
        problem: ProblemData,
        routes: tuple[Route, ...],
        original: tuple[float, float],
        config: PipelineConfig,
        ceiling: float,
    ) -> bool:
        try:
            SolutionValidator().validate(problem, routes, cost_limit=ceiling)
        except (SolutionError, ValueError):
            return False
        cost, balance = objective_vector(problem, routes)
        slack = config.cost_slack(original[0])
        return cost < original[0] - slack or (abs(cost - original[0]) <= slack and balance < original[1])

    def _neighbors(self, problem: ProblemData, routes: tuple[Route, ...]) -> Iterator[tuple[Route, ...]]:
        used = {r.vehicle_id for r in routes}
        expanded = routes + tuple(Route(v.identifier, ()) for v in problem.vehicles if v.identifier not in used)
        yield from self._relocate(expanded)
        yield from self._swap(routes)
        yield from self._two_opt(routes)

    @staticmethod
    def _replace(routes: tuple[Route, ...], changes: dict[int, tuple[str, ...]]) -> tuple[Route, ...]:
        return tuple(
            Route(route.vehicle_id, changes.get(i, route.customers))
            for i, route in enumerate(routes)
            if changes.get(i, route.customers)
        )

    def _relocate(self, routes: tuple[Route, ...]) -> Iterator[tuple[Route, ...]]:
        for source, route in enumerate(routes):
            for position, client in enumerate(route.customers):
                shortened = route.customers[:position] + route.customers[position + 1 :]
                for target, other in enumerate(routes):
                    if source == target:
                        continue
                    for insertion in range(len(other.customers) + 1):
                        expanded = other.customers[:insertion] + (client,) + other.customers[insertion:]
                        yield self._replace(routes, {source: shortened, target: expanded})

    def _swap(self, routes: tuple[Route, ...]) -> Iterator[tuple[Route, ...]]:
        for source, route in enumerate(routes):
            for target in range(source + 1, len(routes)):
                other = routes[target]
                for i, client in enumerate(route.customers):
                    for j, other_client in enumerate(other.customers):
                        first = route.customers[:i] + (other_client,) + route.customers[i + 1 :]
                        second = other.customers[:j] + (client,) + other.customers[j + 1 :]
                        yield self._replace(routes, {source: first, target: second})

    def _two_opt(self, routes: tuple[Route, ...]) -> Iterator[tuple[Route, ...]]:
        for index, route in enumerate(routes):
            for begin in range(len(route.customers) - 1):
                for end in range(begin + 2, len(route.customers) + 1):
                    changed = (
                        route.customers[:begin] + tuple(reversed(route.customers[begin:end])) + route.customers[end:]
                    )
                    yield self._replace(routes, {index: changed})
