"""Compara tempo, memória e qualidade dos backends em processos independentes."""

from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
from dataclasses import asdict
from math import cos, pi, sin
from pathlib import Path
from statistics import median
from time import perf_counter

from cvrp import CVRPPipeline, InstanceTransformer, PipelineConfig
from cvrp.config import Backend
from cvrp.io.writer import ReportWriter
from cvrp.model import CVRPBuilderCplex, CVRPBuilderDocplex
from cvrp.validation.solution import objective_vector


def create_input(customers: int, vehicles: int) -> dict:
    """Cria dados homogêneos, com capacidade suficiente e grafo completo."""
    date, depot = "2026-08-07", "CD-BENCH"
    clients = []
    orders = []
    for index in range(customers):
        angle = 2 * pi * index / customers
        code = f"C-{index + 1:05d}"
        clients.append(
            {
                "codigo": code,
                "razao_social": f"Cliente {index + 1}",
                "cd_atendimento": depot,
                "latitude": -19.92 + 0.1 * sin(angle),
                "longitude": -43.94 + 0.1 * cos(angle),
            }
        )
        orders.append(
            {
                "numero": f"PD-{index + 1:05d}",
                "cliente": code,
                "status": "CONFIRMADO",
                "data_entrega": date,
                "itens": [{"sku": "SKU-BENCH", "quantidade_caixas": 1}],
            }
        )
    return {
        "metadata": {"data_referencia": date},
        "parametros_operacionais": {"custo_por_km": 4.85, "custo_fixo_por_veiculo": 180, "moeda": "BRL"},
        "centros_distribuicao": [{"codigo": depot, "ativo": True, "latitude": -19.92, "longitude": -43.94}],
        "catalogo_produtos": [{"sku": "SKU-BENCH", "peso_kg_caixa": 10, "volume_m3_caixa": 0.01}],
        "clientes": clients,
        "pedidos": orders,
        "frota": {
            "tipos": [
                {
                    "codigo": "BENCH",
                    "capacidade_kg": customers * 10,
                    "capacidade_m3": customers * 0.01,
                    "custo_km_relativo": 1,
                }
            ],
            "disponibilidade": [{"cd": depot, "tipo": "BENCH", "quantidade": vehicles, "em_manutencao": 0}],
        },
        "restricoes_circulacao": [],
        "distancias_conhecidas": [],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("customers", type=int)
    parser.add_argument("vehicles", type=int)
    parser.add_argument("--mode", choices=("build", "pipeline", "both"), default="both")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--clusters", type=int, default=1)
    parser.add_argument("--parallel", action="store_true")
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--time-limit", type=float, default=30)
    parser.add_argument("--post-seconds", type=float, default=5)
    parser.add_argument("--output", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--cplex-log", action="store_true")
    parser.add_argument("--worker", choices=("cplex", "docplex"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.customers, args.vehicles, args.repetitions) < 1:
        parser.error("customers, vehicles e repetitions devem ser positivos")
    return args


def _build_sample(raw: dict, config: PipelineConfig) -> dict[str, object]:
    started = perf_counter()
    data = InstanceTransformer(raw, "CD-BENCH").transform()
    transform_seconds = perf_counter() - started
    builder = CVRPBuilderCplex(data, config) if config.backend == "cplex" else CVRPBuilderDocplex(data, config)
    try:
        started = perf_counter()
        builder.build()
        return {
            "status": "built",
            "build_seconds": perf_counter() - started,
            "transform_seconds": transform_seconds,
            "variables": builder.variable_count,
            "constraints": builder.constraint_count,
            "nonzeros": builder.nonzero_count,
        }
    finally:
        builder.close()


def _pipeline_sample(raw: dict, config: PipelineConfig) -> dict[str, object]:
    pipeline = CVRPPipeline(raw, "CD-BENCH", config=config)
    solution = pipeline.solve()
    assert pipeline.problem is not None
    cost, balance = objective_vector(pipeline.problem, solution.routes)
    started = perf_counter()
    ReportWriter.write(pipeline.problem, solution, config)
    write_seconds = perf_counter() - started
    return {
        "status": solution.status,
        "timings": solution.timings,
        "write_seconds": write_seconds,
        "cost": cost,
        "balance": balance,
        "routes": len(solution.routes),
        "variables": sum(s.variable_count for s in solution.splits),
        "constraints": sum(s.constraint_count for s in solution.splits),
        "nonzeros": sum(s.nonzero_count for s in solution.splits),
        "objectives": [asdict(stage) for split in solution.splits for stage in split.stages],
    }


def _worker(args: argparse.Namespace) -> None:
    config = PipelineConfig(
        backend=args.worker,
        clusters=args.clusters,
        parallel=args.parallel,
        solver_threads=args.threads,
        workers=args.workers,
        cpu_budget=max(args.threads, args.threads * args.workers),
        solve_seconds=args.time_limit,
        postprocess_seconds=args.post_seconds,
        cplex_log=args.cplex_log,
        output_dir=args.output,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    raw = create_input(args.customers, args.vehicles)
    (args.output / "input.json").write_text(json.dumps(raw, indent=2), encoding="utf-8")
    started = perf_counter()
    sample = _build_sample(raw, config) if args.mode == "build" else _pipeline_sample(raw, config)
    unit = 1_048_576 if sys.platform == "darwin" else 1024
    sample.update(
        backend=args.worker,
        mode=args.mode,
        total_seconds=perf_counter() - started,
        peak_rss_parent_mb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / unit,
        peak_rss_children_max_mb=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / unit,
        configuration=asdict(config) | {"output_dir": str(config.output_dir)},
    )
    (args.output / "metrics.json").write_text(json.dumps(sample, indent=2, allow_nan=False), encoding="utf-8")


def _command(args: argparse.Namespace, backend: Backend, mode: str, folder: Path) -> list[str]:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve()),
        str(args.customers),
        str(args.vehicles),
        "--worker",
        backend,
        "--mode",
        mode,
        "--output",
        str(folder),
        "--clusters",
        str(args.clusters),
        "--threads",
        str(args.threads),
        "--workers",
        str(args.workers),
        "--time-limit",
        str(args.time_limit),
        "--post-seconds",
        str(args.post_seconds),
    ]
    if args.parallel:
        cmd.append("--parallel")
    if args.cplex_log:
        cmd.append("--cplex-log")
    return cmd


def main() -> None:
    args = parse_args()
    if args.worker:
        _worker(args)
        return
    modes = ("build", "pipeline") if args.mode == "both" else (args.mode,)
    samples: list[dict] = []
    for mode in modes:
        for repetition in range(args.repetitions):
            backends: tuple[Backend, ...] = ("cplex", "docplex") if repetition % 2 == 0 else ("docplex", "cplex")
            for backend in backends:
                folder = args.output / f"{mode}-{backend}-{repetition + 1}"
                subprocess.run(_command(args, backend, mode, folder), check=True)
                samples.append(json.loads((folder / "metrics.json").read_text(encoding="utf-8")))
    summaries = []
    for mode in modes:
        for backend in ("cplex", "docplex"):
            group = [s for s in samples if s["mode"] == mode and s["backend"] == backend]
            times = [s["total_seconds"] for s in group]
            summary = {
                "mode": mode,
                "backend": backend,
                "median_seconds": median(times),
                "min_seconds": min(times),
                "max_seconds": max(times),
                "statuses": [s["status"] for s in group],
            }
            summaries.append(summary)
            print(f"{mode:8s} {backend:7s} median={median(times):.6f}s min={min(times):.6f}s max={max(times):.6f}s")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "benchmark-summary.json").write_text(
        json.dumps({"samples": samples, "summaries": summaries}, indent=2, allow_nan=False), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
