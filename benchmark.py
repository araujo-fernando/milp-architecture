"""Gera uma instância sintética CVRP e mede uma execução completa do pipeline."""

from __future__ import annotations

import argparse
import json
from math import cos, pi, sin
from pathlib import Path
from time import perf_counter

from architecture_example import CVRPPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("customers", type=int, help="Quantidade de clientes.")
    parser.add_argument("vehicles", type=int, help="Quantidade de veículos disponíveis.")
    parser.add_argument("output", type=Path, help="Caminho do JSON de entrada a gerar.")
    args = parser.parse_args()
    if args.customers < 1 or args.vehicles < 1:
        parser.error("customers e vehicles devem ser inteiros positivos")
    return args


def create_input(customers: int, vehicles: int) -> dict:
    """Cria dados homogêneos, com capacidade suficiente e grafo completo."""
    date, depot = "2026-08-07", "CD-BENCH"
    clients = []
    orders = []
    for index in range(customers):
        angle = 2 * pi * index / customers
        code = f"C-{index + 1:05d}"
        clients.append({"codigo": code, "razao_social": f"Cliente {index + 1}", "cd_atendimento": depot, "latitude": -19.92 + 0.1 * sin(angle), "longitude": -43.94 + 0.1 * cos(angle)})
        orders.append({"numero": f"PD-{index + 1:05d}", "cliente": code, "status": "CONFIRMADO", "data_entrega": date, "itens": [{"sku": "SKU-BENCH", "quantidade_caixas": 1}]})
    return {"metadata": {"data_referencia": date}, "parametros_operacionais": {"custo_por_km": 4.85, "custo_fixo_por_veiculo": 180, "moeda": "BRL"}, "centros_distribuicao": [{"codigo": depot, "ativo": True, "latitude": -19.92, "longitude": -43.94}], "catalogo_produtos": [{"sku": "SKU-BENCH", "peso_kg_caixa": 10, "volume_m3_caixa": 0.01}], "clientes": clients, "pedidos": orders, "frota": {"tipos": [{"codigo": "BENCH", "capacidade_kg": customers * 10, "capacidade_m3": customers * 0.01, "custo_km_relativo": 1}], "disponibilidade": [{"cd": depot, "tipo": "BENCH", "quantidade": vehicles, "em_manutencao": 0}]}, "restricoes_circulacao": [], "distancias_conhecidas": []}


def main() -> None:
    args = parse_args()
    total_started = perf_counter()
    data = create_input(args.customers, args.vehicles)
    write_started = perf_counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    write_seconds = perf_counter() - write_started
    pipeline_started = perf_counter()
    result = CVRPPipeline(data, "CD-BENCH").run()
    pipeline_seconds = perf_counter() - pipeline_started
    print(f"input: {args.output}")
    print(f"write_s: {write_seconds:.4f}")
    print(f"pipeline_s: {pipeline_seconds:.4f}")
    print(f"total_s: {perf_counter() - total_started:.4f}")
    print(f"objective: {result['status_solver']['objetivo']:.2f}")


if __name__ == "__main__":
    main()
