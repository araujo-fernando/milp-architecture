"""Gera uma instância sintética CVRP e mede uma execução completa do pipeline."""

from __future__ import annotations

import argparse
import json
from math import cos, pi, sin
from pathlib import Path
from time import perf_counter

from architecture_example import CVRPPipeline
from architecture_example.instrumentation import configure_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("customers", type=int, help="Quantidade de clientes.")
    parser.add_argument("vehicles", type=int, help="Quantidade de veículos disponíveis.")
    parser.add_argument("--cplex-log", action="store_true", help="Exibe o log do CPLEX durante a resolução.")
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
    scenario_path = Path("data") / f"{args.customers}c-{args.vehicles}v"
    input_path = scenario_path / "input.json"
    output_path = scenario_path / "output.json"
    configure_logging(scenario_path / "execution.log", force=True)
    total_started = perf_counter()
    data = create_input(args.customers, args.vehicles)
    write_started = perf_counter()
    scenario_path.mkdir(parents=True, exist_ok=True)
    input_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
    write_seconds = perf_counter() - write_started
    pipeline_started = perf_counter()
    result = CVRPPipeline(data, "CD-BENCH", cplex_log=args.cplex_log).run()
    pipeline_seconds = perf_counter() - pipeline_started
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=4), encoding="utf-8")
    print(f"input: {input_path}")
    print(f"output: {output_path}")
    print(f"write_s: {write_seconds:.4f}")
    print(f"pipeline_s: {pipeline_seconds:.4f}")
    print(f"total_s: {perf_counter() - total_started:.4f}")
    print(f"objective: {result['status_solver']['objetivo']:.2f}")


if __name__ == "__main__":
    main()
