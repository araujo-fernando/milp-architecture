from __future__ import annotations

import pytest

from cvrp.instrumentation import Instrumentation as inst
from cvrp.transform import InputError, InstanceTransformer


def test_transform_applies_business_rules_and_sparse_arcs(raw: dict) -> None:
    data = InstanceTransformer(raw, "CD").transform()

    assert data.nodes == ("CD", "C1", "C2")
    assert data.demand_kg == {1: 20.0, 2: 30.0}
    assert data.distance[0, 1] == 3
    assert len(data.vehicles) == 2
    blocked_vehicle = next(k for k, vehicle in enumerate(data.vehicles) if vehicle.kind == "TOCO")
    assert (0, 2, blocked_vehicle) not in data.valid_ijk
    assert {item["motivo"] for item in data.discarded} == {"coordenada_ausente", "cliente_nao_cadastrado"}


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
