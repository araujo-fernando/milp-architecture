from __future__ import annotations

import json

import pytest

from architecture_example import __main__ as cli
from architecture_example.instrumentation import Instrumentation as inst
from architecture_example.model import CVRPBuilderCplex, CVRPBuilderDocplex
from architecture_example.pipeline import CVRPPipeline
from architecture_example.solve import LinearConstraint, Solver
from architecture_example.transform import InputError, InstanceTransformer
from benchmark import create_input


@pytest.fixture
def raw() -> dict:
    return {
        "metadata": {"data_referencia": "2026-08-07"},
        "parametros_operacionais": {"custo_por_km": 5, "custo_fixo_por_veiculo": 100, "moeda": "BRL"},
        "centros_distribuicao": [{"codigo": "CD", "ativo": True, "latitude": 0, "longitude": 0}],
        "catalogo_produtos": [{"sku": "A", "peso_kg_caixa": 10, "volume_m3_caixa": 1}],
        "clientes": [
            {"codigo": "C1", "razao_social": "Um", "cd_atendimento": "CD", "latitude": 0, "longitude": 0.1},
            {"codigo": "C2", "razao_social": "Dois", "cd_atendimento": "CD", "latitude": 0.1, "longitude": 0},
            {"codigo": "C3", "razao_social": "Três", "cd_atendimento": "CD", "latitude": None, "longitude": None},
        ],
        "pedidos": [
            {"numero": "1", "cliente": "C1", "status": "CONFIRMADO", "data_entrega": "2026-08-07", "itens": [{"sku": "A", "quantidade_caixas": 2}]},
            {"numero": "1", "cliente": "C1", "status": "CONFIRMADO", "data_entrega": "2026-08-07", "itens": [{"sku": "A", "quantidade_caixas": 2}]},
            {"numero": "2", "cliente": "C2", "status": "CONFIRMADO", "data_entrega": "2026-08-07", "itens": [{"sku": "A", "quantidade_caixas": 3}]},
            {"numero": "3", "cliente": "C3", "status": "CONFIRMADO", "data_entrega": "2026-08-07", "itens": [{"sku": "A", "quantidade_caixas": 1}]},
            {"numero": "4", "cliente": "UNKNOWN", "status": "CONFIRMADO", "data_entrega": "2026-08-07", "itens": [{"sku": "A", "quantidade_caixas": 1}]},
            {"numero": "5", "cliente": "C1", "status": "CANCELADO", "data_entrega": "2026-08-07", "itens": [{"sku": "A", "quantidade_caixas": 9}]},
        ],
        "frota": {"tipos": [
            {"codigo": "VUC", "capacidade_kg": 50, "capacidade_m3": 5, "custo_km_relativo": 1},
            {"codigo": "TOCO", "capacidade_kg": 100, "capacidade_m3": 10, "custo_km_relativo": 2},
        ], "disponibilidade": [
            {"cd": "CD", "tipo": "VUC", "quantidade": 2, "em_manutencao": 1},
            {"cd": "CD", "tipo": "TOCO", "quantidade": 1, "em_manutencao": 0},
        ]},
        "restricoes_circulacao": [{"cd": "CD", "tipo_veiculo": "TOCO", "clientes_bloqueados": ["C2"]}],
        "distancias_conhecidas": [{"origem": "CD", "destino": "C1", "distancia_km": 3}],
    }


def test_transform_applies_business_rules_and_sparse_arcs(raw: dict) -> None:
    data = InstanceTransformer(raw, "CD").transform()

    assert data.nodes == ("CD", "C1", "C2")
    assert data.demand_kg == {1: 20.0, 2: 30.0}
    assert data.distance[0, 1] == 3
    assert len(data.vehicles) == 2
    assert (0, 2, 1) not in data.valid_ijk
    assert {item["motivo"] for item in data.discarded} == {"coordenada_ausente", "cliente_nao_cadastrado"}


def test_builder_creates_three_index_model_with_dfj_constraints(raw: dict) -> None:
    builder = CVRPBuilderDocplex(InstanceTransformer(raw, "CD").transform())
    model = builder.build()

    assert len(builder.x) == len(builder.data.valid_ijk)
    assert len(builder.y) == len(builder.data.nodes) * len(builder.data.vehicles)
    assert model.number_of_variables == len(builder.x) + len(builder.y)
    assert model.number_of_constraints > 20


def test_cplex_builder_creates_the_same_model_size(raw: dict) -> None:
    data = InstanceTransformer(raw, "CD").transform()
    docplex_model = CVRPBuilderDocplex(data).build()
    cplex_builder = CVRPBuilderCplex(data)
    cplex_builder.build()

    assert cplex_builder.solver.variable_count == docplex_model.number_of_variables
    assert cplex_builder.solver.constraint_count == docplex_model.number_of_constraints


def test_cplex_builder_adds_explicit_dfj_rows_for_complete_graph() -> None:
    data = InstanceTransformer(create_input(customers=3, vehicles=2), "CD-BENCH").transform()
    builder = CVRPBuilderCplex(data)
    builder.build()

    # R7 has one row for every non-singleton customer subset and vehicle:
    # (C(3, 2) + C(3, 3)) * 2 = 8. The remaining formulation rows total 24.
    assert builder.solver.constraint_count == 32


def test_pipeline_runs_with_cplex_builder() -> None:
    result = CVRPPipeline(create_input(customers=2, vehicles=1), "CD-BENCH", builder="cplex").run()

    assert result["status_solver"]["num_variaveis"] == 9
    assert result["status_solver"]["num_restricoes"] == 12


@pytest.mark.parametrize(("customers", "expected_variables"), [(1, 4), (3, 16), (5, 36)])
def test_model_size_scales_with_customer_count(customers: int, expected_variables: int) -> None:
    """A complete one-vehicle graph has n(n + 1) arc vars and n + 1 assignment vars."""
    data = InstanceTransformer(create_input(customers, vehicles=1), "CD-BENCH").transform()
    model = CVRPBuilderDocplex(data).build()

    assert model.number_of_variables == expected_variables


def test_invalid_sku_and_insufficient_capacity_are_rejected(raw: dict) -> None:
    raw["pedidos"][0]["itens"][0]["sku"] = "MISSING"
    with pytest.raises(InputError, match="SKU"):
        InstanceTransformer(raw, "CD").transform()

    raw["pedidos"][0]["itens"][0]["sku"] = "A"
    raw["frota"]["tipos"][0]["capacidade_kg"] = 10
    raw["frota"]["tipos"][1]["capacidade_kg"] = 10
    with pytest.raises(InputError, match="excede"):
        InstanceTransformer(raw, "CD").transform()


def test_unknown_or_inactive_depot_is_rejected(raw: dict) -> None:
    with pytest.raises(InputError, match="não encontrado"):
        InstanceTransformer(raw, "MISSING").transform()

    raw["centros_distribuicao"][0]["ativo"] = False
    with pytest.raises(InputError, match="inativo"):
        InstanceTransformer(raw, "CD").transform()


def test_solver_builds_and_returns_runtime_independent_solution() -> None:
    solver = Solver(problem_name="test")
    (variable,) = solver.add_binary_variables([2.0])
    solver.minimize()
    solver.add_linear_constraints((LinearConstraint([variable], [1.0], "G", 1.0),))

    solution = solver.solve()

    assert solution.status
    assert solution.objective_value == pytest.approx(2.0)
    assert solution.value(variable) == pytest.approx(1.0)


def test_solver_raises_clear_error_for_infeasible_model() -> None:
    solver = Solver(problem_name="infeasible")
    (variable,) = solver.add_binary_variables([0.0])
    solver.minimize()
    solver.add_linear_constraints(
        (
            LinearConstraint([variable], [1.0], "L", 0.0),
            LinearConstraint([variable], [1.0], "G", 1.0),
        )
    )
    with pytest.raises(RuntimeError, match="Solver"):
        solver.solve()


def test_instrumentation_times_blocks_and_decorated_calls(tmp_path) -> None:
    inst.configure(tmp_path / "execution.log", force=True)

    with inst.measure("bloco de teste") as measurement:
        pass

    @inst.log_execution_time
    def add(left: int, right: int) -> int:
        return left + right

    assert measurement.elapsed_seconds >= 0
    assert add(1, 2) == 3
    assert add.__name__ == "add"
    assert "bloco de teste" in (tmp_path / "execution.log").read_text(encoding="utf-8")


def test_pipeline_orchestrates_layers(raw: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    class Builder:
        class model:
            number_of_variables = 1
            number_of_constraints = 2

            @staticmethod
            def solve(**kwargs: object) -> str:
                assert kwargs == {"log_output": False}
                return "solution"

        def __init__(self, data: object) -> None:
            self.data = data

        def build(self) -> None:
            return None

    class Transformer:
        def __init__(self, *_: object) -> None:
            pass

        def transform(self) -> str:
            return "data"

    class Reporter:
        def __init__(self, *args: object) -> None:
            self.args = args

        def extract(self) -> dict[str, str]:
            return {"ok": self.args[0]}

    monkeypatch.setattr("architecture_example.pipeline.InstanceTransformer", Transformer)
    monkeypatch.setattr("architecture_example.pipeline.CVRPBuilderDocplex", Builder)
    monkeypatch.setattr("architecture_example.pipeline.SolutionReporter", Reporter)

    assert CVRPPipeline(raw, "CD").run() == {"ok": "data"}


@pytest.mark.parametrize(("extra_args", "cplex_log"), [([], False), (["--cplex-log"], True)])
def test_cli_keeps_scenario_artifacts_together(
    tmp_path, monkeypatch: pytest.MonkeyPatch, extra_args: list[str], cplex_log: bool
) -> None:
    scenario = tmp_path / "scenario"
    scenario.mkdir()
    (scenario / "input.json").write_text(json.dumps({"input": True}), encoding="utf-8")
    captured: dict[str, object] = {}

    class Pipeline:
        def __init__(self, raw: dict, cd: str, date: str | None, *, cplex_log: bool = False) -> None:
            captured.update(raw=raw, cd=cd, date=date, cplex_log=cplex_log)

        def run(self) -> dict[str, bool]:
            return {"solved": True}

    monkeypatch.setattr(cli, "CVRPPipeline", Pipeline)
    monkeypatch.setattr("sys.argv", ["architecture-example", str(scenario), "CD", "--date", "2026-08-07", *extra_args])
    cli.main()

    assert captured == {"raw": {"input": True}, "cd": "CD", "date": "2026-08-07", "cplex_log": cplex_log}
    assert json.loads((scenario / "output.json").read_text(encoding="utf-8")) == {"solved": True}
    assert (scenario / "execution.log").exists()
