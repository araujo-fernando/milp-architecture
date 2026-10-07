"""Contratos de partição e melhoria local, sem depender do runtime CPLEX."""

from dataclasses import replace
from time import perf_counter

import pytest

from cvrp.config import PipelineConfig
from cvrp.domain.instance import Customer, Location, ProblemData, ProblemSplit, TravelData, Vehicle
from cvrp.domain.results import Route
from cvrp.postprocess import LocalSearch
from cvrp.preprocess import ClusterPreprocessor
from cvrp.validation.solution import SolutionError, SolutionValidator, objective_vector, route_metrics


def problem_data(count: int = 4, fleet: int = 2, capacity: float = 10) -> ProblemData:
    depot = Location("D", "Depósito", 0, 0)
    customers = {
        str(i): Customer(Location(str(i), str(i), float(i), float(i)), 1, 1, (f"P{i}",)) for i in range(1, count + 1)
    }
    vehicles = tuple(Vehicle(f"V{i}", "T", capacity, capacity, 1) for i in range(fleet))
    locations = {"D": depot} | {c: customer.location for c, customer in customers.items()}
    overrides = {(a, b): 1.0 for a in locations for b in locations if a != b}
    return ProblemData(depot, "2026-10-07", customers, vehicles, TravelData(locations, overrides, {}), 0, "BRL")


def test_partition_is_complete_exclusive_reproducible_and_uses_no_distances(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = problem_data(8, 4)

    def forbidden_distance(self: TravelData, origin: str, destination: str) -> float:
        raise AssertionError("Distâncias devem ser materializadas após os splits")

    monkeypatch.setattr(TravelData, "distance", forbidden_distance)
    pre = ClusterPreprocessor()
    splits = pre.split(problem, PipelineConfig())
    assert splits == pre.split(problem, PipelineConfig())
    assert len(splits) == 4
    assert sorted(c for split in splits for c in split.customer_ids) == sorted(problem.customers)
    vehicles = [v.identifier for split in splits for v in split.vehicles]
    assert len(vehicles) == len(set(vehicles))


def test_coincident_coordinates_reduce_clusters_and_empty_input() -> None:
    problem = problem_data()
    customers = {
        c: replace(customer, location=replace(customer.location, latitude=0, longitude=0))
        for c, customer in problem.customers.items()
    }
    pre = ClusterPreprocessor()
    assert len(pre.split(replace(problem, customers=customers), PipelineConfig())) == 1
    assert "clusters_reduzidos" in {d.code for d in pre.diagnostics}
    assert pre.split(replace(problem, customers={}), PipelineConfig()) == ()
    assert pre.diagnostics == ()


def test_greedy_partition_failure_falls_back_without_declaring_infeasibility() -> None:
    problem = problem_data(4, 2, capacity=2)
    # Both geographic clusters need the sole vehicle able to circulate at 1 and 4.
    vehicles = (
        replace(problem.vehicles[0], kind="T0", capacity_kg=3, capacity_m3=3),
        replace(problem.vehicles[1], kind="T1"),
    )
    travel = replace(problem.travel, blocked={"T1": frozenset({"1", "4"})})
    pre = ClusterPreprocessor()
    result = pre.split(replace(problem, vehicles=vehicles, travel=travel), PipelineConfig(clusters=2))
    assert len(result) == 1
    assert result[0].vehicles == vehicles
    assert "alocacao_frota_falhou" in {d.code for d in pre.diagnostics}
    assert "fallback_problema_unico" in {d.code for d in pre.diagnostics}


def test_partition_validation_rejects_reused_vehicle_and_ineligible_allocation() -> None:
    problem = problem_data(2)
    pre = ClusterPreprocessor()
    reused = (ProblemSplit("a", ("1",), (problem.vehicles[0],)), ProblemSplit("b", ("2",), (problem.vehicles[0],)))
    with pytest.raises(ValueError, match="exclusiva"):
        pre.validate_splits(problem, reused)
    invalid = replace(problem, travel=replace(problem.travel, blocked={"T": frozenset({"2"})}))
    with pytest.raises(ValueError, match="elegível"):
        pre.split(invalid, PipelineConfig(clusters=1))
    with pytest.raises(ValueError, match="partição"):
        pre.validate_splits(problem, (ProblemSplit("a", ("1",), problem.vehicles),))


def test_metrics_recalculate_directional_cost_and_balance_excludes_idle() -> None:
    problem = problem_data(2)
    overrides = problem.travel.overrides | {("D", "1"): 2, ("1", "2"): 3, ("2", "D"): 4, ("2", "1"): 30}
    problem = replace(problem, fixed_vehicle_cost=7, travel=replace(problem.travel, overrides=overrides))
    route = Route("V0", ("1", "2"))
    metrics = route_metrics(problem, route)
    assert metrics.distance_km == 9
    assert metrics.total_cost == 16
    assert metrics.load_kg == metrics.load_m3 == 2
    assert objective_vector(problem, (route,)) == (16, 0)
    assert route_metrics(problem, Route("V1", ())).total_cost == 0


@pytest.mark.parametrize(
    "routes, message",
    [
        ((Route("V0", ("1", "1", "2")),), "exatamente uma vez"),
        ((Route("V0", ("1",)),), "exatamente uma vez"),
        ((Route("V0", ("1",)), Route("V0", ("2",))), "mais de uma rota"),
        ((Route("INVALID", ("1", "2")),), "autorizada"),
        ((Route("V0", ()), Route("V1", ("1", "2"))), "vazia"),
    ],
)
def test_validator_rejects_invalid_routes(routes: tuple[Route, ...], message: str) -> None:
    with pytest.raises(SolutionError, match=message):
        SolutionValidator().validate(problem_data(2), routes)


def test_validator_rejects_capacity_arcs_cost_limit_and_accepts_split_contract() -> None:
    problem = problem_data(2)
    route = (Route("V0", ("1", "2")),)
    validator = SolutionValidator()
    validator.validate(problem, (Route("V1", ("2",)),), expected_customers=("2",), allowed_vehicles=("V1",))
    with pytest.raises(SolutionError, match="kg"):
        validator.validate(replace(problem, vehicles=(replace(problem.vehicles[0], capacity_kg=1),)), route)
    with pytest.raises(SolutionError, match="m³"):
        validator.validate(replace(problem, vehicles=(replace(problem.vehicles[0], capacity_m3=1),)), route)
    with pytest.raises(SolutionError, match="proibidos"):
        validator.validate(replace(problem, travel=replace(problem.travel, blocked={"T": frozenset({"2"})})), route)
    with pytest.raises(SolutionError, match="custo"):
        validator.validate(problem, route, cost_limit=2)


def test_relocate_improves_balance_at_equivalent_cost() -> None:
    problem = problem_data(4)
    # Route distance consists entirely of customer service cost, so relocating preserves cost.
    overrides = {(a, b): (0.0 if b == "D" else 1.0) for a, b in problem.travel.overrides}
    problem = replace(problem, travel=replace(problem.travel, overrides=overrides))
    routes = (Route("V0", ("1", "2", "3")), Route("V1", ("4",)))
    result = LocalSearch().improve(problem, routes, PipelineConfig())
    assert result.balance_before == 2
    assert result.balance_after == 0
    assert result.cost_before == result.cost_after == 4
    assert result.accepted_moves == 1
    SolutionValidator().validate(problem, result.routes)


def test_postprocess_limits_and_disabled_leave_valid_seed() -> None:
    problem = problem_data(2)
    routes = (Route("V0", ("1", "2")),)
    search = LocalSearch()
    disabled = search.improve(problem, routes, PipelineConfig(postprocess_seconds=0))
    assert disabled.routes == routes and disabled.candidates == 0
    assert disabled.stop_reason == "time_limit"
    expired = search.improve(problem, routes, PipelineConfig(), deadline=perf_counter() - 1)
    assert expired.routes == routes and expired.candidates == 0
    limited = search.improve(problem, routes, PipelineConfig(postprocess_candidates=1))
    assert limited.candidates == 1
    assert limited.stop_reason == "candidate_limit"
    empty = search.improve(replace(problem, customers={}), (), PipelineConfig())
    assert empty.routes == () and empty.stop_reason == "local_optimum"


def test_two_opt_uses_internal_directed_arcs_and_rejects_costlier_reversal() -> None:
    problem = problem_data(3, 1)
    overrides = {key: 20.0 for key in problem.travel.overrides}
    overrides.update(
        {("D", "1"): 1, ("1", "2"): 1, ("2", "3"): 1, ("3", "D"): 1, ("D", "2"): 0, ("1", "3"): 0, ("2", "1"): 20}
    )
    problem = replace(problem, travel=replace(problem.travel, overrides=overrides))
    routes = (Route("V0", ("1", "2", "3")),)
    result = LocalSearch().improve(problem, routes, PipelineConfig())
    assert result.routes == routes
    assert result.cost_after == 4
    # Reversal becomes a real improvement when the reversed internal arc is cheap.
    overrides[("2", "1")] = 0
    improved = LocalSearch().improve(problem, routes, PipelineConfig())
    assert improved.cost_after < improved.cost_before
    assert improved.routes[0].customers == ("2", "1", "3")


def test_postprocess_never_exceeds_original_cost_tolerance() -> None:
    problem = problem_data(8, 3)
    overrides = {(a, b): (0.0 if b == "D" else 1.0) for a, b in problem.travel.overrides}
    problem = replace(problem, fixed_vehicle_cost=0.7, travel=replace(problem.travel, overrides=overrides))
    routes = (Route("V0", ("1", "2", "3", "4", "5", "6")), Route("V1", ("7", "8")))
    config = PipelineConfig(absolute_tolerance=0.5)
    result = LocalSearch().improve(problem, routes, config)
    assert result.cost_after <= result.cost_before + 0.5
    assert len(result.routes) == 2
    assert result.balance_after < result.balance_before
    SolutionValidator().validate(problem, result.routes, cost_limit=result.cost_before + 0.5)


def test_swap_improves_cost_when_relocate_would_overload_both_routes() -> None:
    problem = problem_data(4, 2, capacity=2)
    overrides = {key: 10.0 for key in problem.travel.overrides}
    overrides.update({("D", "1"): 1, ("D", "3"): 1, ("3", "2"): 1, ("1", "4"): 1, ("2", "D"): 1, ("4", "D"): 1})
    problem = replace(problem, travel=replace(problem.travel, overrides=overrides))
    routes = (Route("V0", ("1", "2")), Route("V1", ("3", "4")))
    result = LocalSearch().improve(problem, routes, PipelineConfig())
    assert result.cost_before == 24
    assert result.cost_after == 6
    assert result.balance_before == result.balance_after == 0
    SolutionValidator().validate(problem, result.routes)


def test_best_accepted_move_survives_candidate_limit() -> None:
    problem = problem_data(2, 1)
    overrides = problem.travel.overrides | {("1", "2"): 10}
    problem = replace(problem, travel=replace(problem.travel, overrides=overrides))
    routes = (Route("V0", ("1", "2")),)
    result = LocalSearch().improve(problem, routes, PipelineConfig(postprocess_candidates=1))
    assert result.routes == (Route("V0", ("2", "1")),)
    assert result.accepted_moves == result.candidates == 1
    assert result.stop_reason == "candidate_limit"


def test_provided_only_graph_rejects_missing_reverse_edges_during_local_search() -> None:
    problem = problem_data(3, 1)
    overrides = {("D", "1"): 1.0, ("1", "2"): 1.0, ("2", "3"): 1.0, ("3", "D"): 1.0}
    problem = replace(problem, travel=replace(problem.travel, overrides=overrides, mode="provided_only"))
    routes = (Route("V0", ("1", "2", "3")),)
    result = LocalSearch().improve(problem, routes, PipelineConfig())
    assert result.routes == routes and result.accepted_moves == 0


def test_validator_rejects_nonfinite_metric_and_invalid_seed_even_when_post_disabled() -> None:
    problem = problem_data(2)
    invalid = replace(
        problem, customers=problem.customers | {"1": replace(problem.customers["1"], demand_kg=float("nan"))}
    )
    routes = (Route("V0", ("1", "2")),)
    with pytest.raises(SolutionError, match="inválidas"):
        LocalSearch().improve(invalid, routes, PipelineConfig(postprocess_seconds=0))
    with pytest.raises(SolutionError, match="desconhecido"):
        route_metrics(problem, Route("UNKNOWN", ("1",)))
    with pytest.raises(SolutionError, match="desconhecido"):
        route_metrics(problem, Route("V0", ("UNKNOWN",)))


def test_cost_tolerance_stays_anchored_after_a_large_cost_reduction() -> None:
    problem = problem_data(9, 3)
    overrides = {(a, b): (0.0 if b == "D" else 1.0) for a, b in problem.travel.overrides}
    overrides[("1", "2")] = 100
    vehicles = (problem.vehicles[0], *(replace(v, cost_per_km=1.2) for v in problem.vehicles[1:]))
    problem = replace(problem, vehicles=vehicles, travel=replace(problem.travel, overrides=overrides))
    routes = (Route("V0", ("1", "2", "3", "4", "5", "6", "7")), Route("V1", ("8",)), Route("V2", ("9",)))
    config = PipelineConfig(absolute_tolerance=0.5)
    result = LocalSearch().improve(problem, routes, config)
    assert result.cost_before == pytest.approx(108.4)
    # The first accepted move yields 9.6. Later balancing must stay below its fixed 10.1 ceiling.
    assert result.cost_after <= 9.6 + config.cost_slack(9.6)
    assert result.cost_after < result.cost_before
    assert result.balance_after < result.balance_before


def test_split_contract_rejects_duplicate_ids_empty_members_and_changed_vehicle() -> None:
    problem = problem_data(2, 2, capacity=1)
    first = ProblemSplit("first", ("1",), (problem.vehicles[0],))
    second = ProblemSplit("second", ("2",), (problem.vehicles[1],))
    pre = ClusterPreprocessor()
    with pytest.raises(ValueError, match="únicos"):
        pre.validate_splits(problem, (first, replace(second, identifier="first")))
    with pytest.raises(ValueError, match="não vazios"):
        pre.validate_splits(problem, (replace(first, identifier=""), second))
    with pytest.raises(ValueError, match="vazio"):
        pre.validate_splits(problem, (first, second, ProblemSplit("empty", (), ())))
    changed = replace(problem.vehicles[0], capacity_kg=2, capacity_m3=2)
    with pytest.raises(ValueError, match="canônico"):
        pre.validate_splits(problem, (ProblemSplit("single", ("1", "2"), (changed,)),))
