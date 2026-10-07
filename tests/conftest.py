import pytest


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
            {
                "numero": "1",
                "cliente": "C1",
                "status": "CONFIRMADO",
                "data_entrega": "2026-08-07",
                "itens": [{"sku": "A", "quantidade_caixas": 2}],
            },
            {
                "numero": "1",
                "cliente": "C1",
                "status": "CONFIRMADO",
                "data_entrega": "2026-08-07",
                "itens": [{"sku": "A", "quantidade_caixas": 2}],
            },
            {
                "numero": "2",
                "cliente": "C2",
                "status": "CONFIRMADO",
                "data_entrega": "2026-08-07",
                "itens": [{"sku": "A", "quantidade_caixas": 3}],
            },
            {
                "numero": "3",
                "cliente": "C3",
                "status": "CONFIRMADO",
                "data_entrega": "2026-08-07",
                "itens": [{"sku": "A", "quantidade_caixas": 1}],
            },
            {
                "numero": "4",
                "cliente": "UNKNOWN",
                "status": "CONFIRMADO",
                "data_entrega": "2026-08-07",
                "itens": [{"sku": "A", "quantidade_caixas": 1}],
            },
            {
                "numero": "5",
                "cliente": "C1",
                "status": "CANCELADO",
                "data_entrega": "2026-08-07",
                "itens": [{"sku": "A", "quantidade_caixas": 9}],
            },
        ],
        "frota": {
            "tipos": [
                {"codigo": "VUC", "capacidade_kg": 50, "capacidade_m3": 5, "custo_km_relativo": 1},
                {"codigo": "TOCO", "capacidade_kg": 100, "capacidade_m3": 10, "custo_km_relativo": 2},
            ],
            "disponibilidade": [
                {"cd": "CD", "tipo": "VUC", "quantidade": 2, "em_manutencao": 1},
                {"cd": "CD", "tipo": "TOCO", "quantidade": 1, "em_manutencao": 0},
            ],
        },
        "restricoes_circulacao": [{"cd": "CD", "tipo_veiculo": "TOCO", "clientes_bloqueados": ["C2"]}],
        "distancias_conhecidas": [{"origem": "CD", "destino": "C1", "distancia_km": 3}],
    }
