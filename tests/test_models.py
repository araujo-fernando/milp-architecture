"""Paridade matemática e comportamento nativo dos dois backends."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cplex import Cplex
from docplex.mp.model import Model

from benchmark import create_input
from cvrp.config import PipelineConfig
from cvrp.domain.instance import InstanceData
from cvrp.model import CVRPBuilderCplex, CVRPBuilderDocplex
from cvrp.model.solution import finite_metric
from cvrp.transform import InstanceTransformer

type Builder = CVRPBuilderCplex | CVRPBuilderDocplex


@pytest.fixture(params=[CVRPBuilderDocplex, CVRPBuilderCplex], ids=["docplex", "cplex"])
def builder_type(request: pytest.FixtureRequest) -> type[Builder]:
    return request.param


def instance(customers: int = 4, vehicles: int = 3) -> InstanceData:
    return InstanceTransformer(create_input(customers, vehicles), "CD-BENCH").transform()


@pytest.fixture
def builder(builder_type: type[Builder]) -> Iterator[Builder]:
    built = builder_type(instance(), PipelineConfig(mip_gap=0))
    built.build()
    yield built
    built.close()


def native(builder: Builder) -> Cplex:
    return builder.model if isinstance(builder, CVRPBuilderCplex) else builder.model.get_cplex()


def signature(model: Cplex) -> tuple[object, ...]:
    """Compara variáveis, coeficientes e linhas usando nomes, não posições."""
    variables = model.variables.get_names()
    columns = tuple(
        zip(
            variables,
            model.variables.get_types(),
            model.variables.get_lower_bounds(),
            model.variables.get_upper_bounds(),
            model.objective.get_linear(),
            strict=True,
        )
    )
    rows = tuple(
        (name, sense, rhs, tuple(sorted((variables[i], value) for i, value in zip(row.ind, row.val, strict=True))))
        for name, sense, rhs, row in zip(
            model.linear_constraints.get_names(),
            model.linear_constraints.get_senses(),
            model.linear_constraints.get_rhs(),
            model.linear_constraints.get_rows(),
            strict=True,
        )
    )
    return tuple(sorted(columns)), tuple(sorted(rows)), model.objective.get_sense()


@pytest.mark.parametrize("customers,vehicles", [(1, 1), (3, 2), (5, 1)])
def test_build_size_is_polynomial(builder_type: type[Builder], customers: int, vehicles: int) -> None:
    built = builder_type(instance(customers, vehicles))
    try:
        model = built.build()
        assert isinstance(model, (Model, Cplex))
        assert (
            built.variable_count == customers * (customers + 1) * vehicles + (customers + 1) * vehicles + customers + 2
        )
        assert (
            built.constraint_count
            == customers + 2 * (customers + 1) * vehicles + 5 * vehicles + customers * (customers - 1) * vehicles + 1
        )
        assert built.nonzero_count > built.constraint_count
    finally:
        built.close()


def test_backends_have_identical_native_coefficients(tmp_path: Path) -> None:
    data = instance(3, 2)
    # Zero demanda e custos direcionais são preservados pela formulação.
    data = replace(
        data,
        customers={i: replace(c, demand_kg=0, demand_m3=0) if i == 2 else c for i, c in data.customers.items()},
        cost={key: float(1 + key[0] * 3 + key[1] + key[2]) for key in data.valid_ijk},
    )
    first, second = CVRPBuilderDocplex(data), CVRPBuilderCplex(data)
    try:
        first.build()
        second.build()
        assert signature(native(first)) == signature(native(second))
        assert first.nonzero_count == second.nonzero_count
        first.freeze_cost(500)
        second.freeze_cost(500)
        first.minimize_balance()
        second.minimize_balance()
        assert signature(native(first)) == signature(native(second))
        for name, built in (("docplex", first), ("cplex", second)):
            path = tmp_path / f"{name}.lp"
            built.export(path)
            content = path.read_text()
            assert all(value in content for value in ("x_0_1_0", "y_1_0", "u_1", "r7_1_2_0", "r11", "lex_cost_limit"))
    finally:
        first.close()
        second.close()


def test_sparse_graph_degree_rows_match() -> None:
    data = instance(3, 2)
    keys = tuple(key for key in data.valid_ijk if key[2] == 0 or (key[0] != 2 and key[1] != 2))
    data = replace(
        data,
        valid_ijk=keys,
        cost={key: data.cost[key] for key in keys},
        outgoing={
            key: tuple(j for j in values if (*key[:1], j, key[1]) in keys) for key, values in data.outgoing.items()
        },
        incoming={
            key: tuple(i for i in values if (i, key[0], key[1]) in keys) for key, values in data.incoming.items()
        },
    )
    first, second = CVRPBuilderDocplex(data), CVRPBuilderCplex(data)
    try:
        first.build()
        second.build()
        assert signature(native(first)) == signature(native(second))
        assert "r3_2_1" in native(first).linear_constraints.get_names()
    finally:
        first.close()
        second.close()


def test_known_lexicographic_optimum_and_mip_start(builder_type: type[Builder]) -> None:
    data = instance()
    data = replace(
        data,
        cost={key: 1.0 for key in data.valid_ijk},
        fixed_vehicle_cost=3,
        vehicles=tuple(replace(v, capacity_kg=30) for v in data.vehicles),
    )
    built = builder_type(data, PipelineConfig(mip_gap=0))
    try:
        built.build()
        first, solution = built.solve_stage("cost", 10, "test")
        assert solution is not None and first.proven_optimal
        assert first.value == pytest.approx(12)
        assert first.cost == pytest.approx(solution.cost)
        if isinstance(built, CVRPBuilderDocplex):
            assert built.incumbent is not None
            start_balance = built.incumbent.get_value(built.upper) - built.incumbent.get_value(built.lower)
        else:
            assert built.incumbent is not None
            start_balance = built.incumbent[built.upper] - built.incumbent[built.lower]
        assert start_balance == solution.balance
        built.freeze_cost(solution.cost + 1e-6)
        built.minimize_balance()
        if isinstance(built, CVRPBuilderDocplex):
            assert built.model.number_of_mip_starts > 0
        else:
            assert built.model.MIP_starts.get_num() > 0
            start, _ = built.model.MIP_starts.get_starts(built.model.MIP_starts.get_num() - 1)
            values = dict(zip(start.ind, start.val, strict=True))
            assert values[built.upper] - values[built.lower] == solution.balance
        second, balanced = built.solve_stage("balance", 10, "test")
        assert balanced is not None and second.proven_optimal
        assert second.value == pytest.approx(0)
        assert balanced.balance == pytest.approx(0)
        assert balanced.cost == pytest.approx(12)
        assert len({k for i, _, k in balanced.arcs if i == 0}) == 2
        assert second.objective == "balance" and second.split_id == "test"
        assert second.gap == pytest.approx(0)
    finally:
        built.close()


def test_volume_capacity_and_heterogeneous_travel_cost(builder_type: type[Builder]) -> None:
    data = instance(2, 2)
    data = replace(
        data,
        vehicles=tuple(replace(v, capacity_kg=100, capacity_m3=0.01) for v in data.vehicles),
        cost={key: 1.0 if key[2] == 0 else 3.0 for key in data.valid_ijk},
        fixed_vehicle_cost=3,
    )
    built = builder_type(data, PipelineConfig(mip_gap=0))
    try:
        built.build()
        stage, solution = built.solve_stage("cost", 10, "test")
        assert stage.proven_optimal and solution is not None
        assert solution.cost == pytest.approx(14)
        assert len({k for i, _, k in solution.arcs if i == 0}) == 2
    finally:
        built.close()


def test_zero_demands_cannot_form_disconnected_subtour(builder_type: type[Builder]) -> None:
    data = instance(4, 1)
    data = replace(
        data,
        customers={i: replace(c, demand_kg=0, demand_m3=0) for i, c in data.customers.items()},
        cost={key: float(key[0] == 0 or key[1] == 0) for key in data.valid_ijk},
        fixed_vehicle_cost=0,
    )
    built = builder_type(data, PipelineConfig(mip_gap=0))
    try:
        built.build()
        stage, solution = built.solve_stage("cost", 10, "test")
        assert stage.proven_optimal and solution is not None
        successor = {i: j for i, j, _ in solution.arcs}
        visited, node = set(), successor[0]
        while node != 0 and node not in visited:
            visited.add(node)
            node = successor[node]
        assert node == 0 and visited == set(data.customers)
        assert solution.cost == pytest.approx(2)
    finally:
        built.close()


def test_infeasible_model_returns_no_solution(builder_type: type[Builder]) -> None:
    data = instance(2, 1)
    data = replace(data, vehicles=tuple(replace(v, capacity_kg=15) for v in data.vehicles))
    built = builder_type(data)
    try:
        built.build()
        stage, solution = built.solve_stage("cost", 10, "test")
        assert solution is None and not stage.has_incumbent and not stage.proven_optimal
        assert stage.value is stage.cost is stage.balance is stage.gap is None
        assert built.incumbent is None
        assert "infeasible" in stage.status.lower()
    finally:
        built.close()


def test_time_limit_without_incumbent_is_reported(builder: Builder, monkeypatch: pytest.MonkeyPatch) -> None:
    if isinstance(builder, CVRPBuilderDocplex):
        monkeypatch.setattr(builder.model, "solve", lambda **_: None)
        details = SimpleNamespace(status="time limit exceeded", best_bound=7, mip_relative_gap=1e75, status_code=108)
        monkeypatch.setattr(type(builder.model), "solve_details", property(lambda _: details))
    else:
        monkeypatch.setattr(builder.model, "solve", lambda: None)
        solution = SimpleNamespace(
            is_primal_feasible=lambda: False,
            get_status_string=lambda: "time limit exceeded",
            get_status=lambda: 108,
            MIP=SimpleNamespace(get_best_objective=lambda: 7),
        )
        monkeypatch.setattr(builder.model, "solution", solution)
    stage, chosen = builder.solve_stage("cost", 1, "no-incumbent")
    assert chosen is None and not stage.has_incumbent and not stage.proven_optimal
    assert stage.value is stage.cost is stage.balance is stage.gap is None
    assert stage.bound == 7 and stage.seconds >= 0


@pytest.mark.parametrize("value", [None, float("nan"), float("inf"), -float("inf"), 1e75, -1e75])
def test_infinite_solver_metrics_are_missing(value: float | None) -> None:
    assert finite_metric(value) is None


@pytest.mark.parametrize("fleet", [0, 2])
def test_empty_instance_can_build_and_solve_both_stages(builder_type: type[Builder], fleet: int) -> None:
    data = instance(1, fleet or 1)
    data = replace(
        data,
        nodes=(data.depot,),
        customers={},
        vehicles=data.vehicles[:fleet],
        distance={},
        cost={},
        valid_ijk=(),
        outgoing={},
        incoming={},
    )
    built = builder_type(data, PipelineConfig(mip_gap=0))
    try:
        built.build()
        first, initial = built.solve_stage("cost", 10, "empty")
        assert first.proven_optimal and initial is not None
        assert initial.arcs == () and initial.cost == initial.balance == 0
        built.freeze_cost(0)
        built.minimize_balance()
        second, final = built.solve_stage("balance", 10, "empty")
        assert second.proven_optimal and final == initial
        assert second.value == 0
        if fleet == 0:
            assert first.bound is first.gap is second.bound is second.gap is None
    finally:
        built.close()


def test_solver_memory_configuration_is_native(builder: Builder) -> None:
    model = builder.model
    assert model.parameters.workmem.get() == builder.config.solver_work_memory_mb
    assert model.parameters.mip.strategy.file.get() == 3
