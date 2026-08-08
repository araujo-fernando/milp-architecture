"""Gera uma instância sintética CVRP e mede uma execução completa do pipeline."""

from __future__ import annotations

import argparse
import json
from math import cos, pi, sin
from pathlib import Path

from architecture_example import CVRPPipeline
from architecture_example.instrumentation import Instrumentation as inst


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
    inst.configure(scenario_path / "execution.log", force=True)
    with inst.measure("benchmark completo") as total_measurement:
        data = create_input(args.customers, args.vehicles)

        with inst.measure("gravação da entrada") as write_measurement:
            scenario_path.mkdir(parents=True, exist_ok=True)
            input_path.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")

        with inst.measure("pipeline CPLEX") as cplex_pipeline_measurement:
            cplex_result = CVRPPipeline(data, "CD-BENCH", builder="cplex", cplex_log=args.cplex_log).run()

        with inst.measure("pipeline Docplex") as docplex_pipeline_measurement:
            docplex_result = CVRPPipeline(data, "CD-BENCH", builder="docplex", cplex_log=args.cplex_log).run()

        scenario_path.joinpath("output_cplex.json").write_text(json.dumps(cplex_result, ensure_ascii=False, indent=4), encoding="utf-8")
        scenario_path.joinpath("output_docplex.json").write_text(json.dumps(docplex_result, ensure_ascii=False, indent=4), encoding="utf-8")

    print(f"\ncplex_pipeline_s: {cplex_pipeline_measurement.elapsed_seconds:.4f}")
    print(f"docplex_pipeline_s: {docplex_pipeline_measurement.elapsed_seconds:.4f}")
    print(f"docplex/cplex_ratio: {docplex_pipeline_measurement.elapsed_seconds/cplex_pipeline_measurement.elapsed_seconds:.4f}")


if __name__ == "__main__":
    main()
