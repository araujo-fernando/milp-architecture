from __future__ import annotations

import pytest

from architecture_example.model import CVRPBuilder
from architecture_example.pipeline import CVRPPipeline
from architecture_example.solve import CVRPSolver
from architecture_example.transform import InputError, InstanceTransformer


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
    builder = CVRPBuilder(InstanceTransformer(raw, "CD").transform())
    model = builder.build()

    assert len(builder.x) == len(builder.data.valid_ijk)
    assert len(builder.y) == len(builder.data.nodes) * len(builder.data.vehicles)
    assert model.number_of_variables == len(builder.x) + len(builder.y)
    assert model.number_of_constraints > 20


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


def test_solver_returns_solution_or_clear_error() -> None:
    class Model:
        def solve(self, **_: object) -> object:
            return "solution"

    assert CVRPSolver(Model()).solve() == "solution"

    class InfeasibleModel:
        def solve(self, **_: object) -> None:
            return None

    with pytest.raises(RuntimeError, match="Solver"):
        CVRPSolver(InfeasibleModel()).solve()


def test_pipeline_orchestrates_layers(raw: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    class Builder:
        model = object()

        def __init__(self, data: object) -> None:
            self.data = data

        def build(self) -> None:
            return None

    class Transformer:
        def __init__(self, *_: object) -> None:
            pass

        def transform(self) -> str:
            return "data"

    class Solver:
        def __init__(self, _: object) -> None:
            pass

        def solve(self) -> str:
            return "solution"

    class Reporter:
        def __init__(self, *args: object) -> None:
            self.args = args

        def extract(self) -> dict[str, str]:
            return {"ok": self.args[0]}

    monkeypatch.setattr("architecture_example.pipeline.InstanceTransformer", Transformer)
    monkeypatch.setattr("architecture_example.pipeline.CVRPBuilder", Builder)
    monkeypatch.setattr("architecture_example.pipeline.CVRPSolver", Solver)
    monkeypatch.setattr("architecture_example.pipeline.SolutionReporter", Reporter)

    assert CVRPPipeline(raw, "CD").run() == {"ok": "data"}
