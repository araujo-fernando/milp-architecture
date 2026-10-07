"""CLI de cenário: dois backends, splits e artefatos equivalentes JSON/Excel."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import PipelineConfig
from .instrumentation import Instrumentation as inst
from .io.reader import InputError, ScenarioReader
from .io.writer import ReportWriter
from .pipeline import CVRPPipeline


def run(
    input_path: Path,
    cd: str,
    date: str | None,
    output_path: Path,
    cplex_log: bool = False,
    *,
    config: PipelineConfig | None = None,
) -> dict[str, object]:
    settings = config or PipelineConfig(output_dir=output_path.parent, cplex_log=cplex_log)
    if settings.output_dir is None:
        settings = replace(settings, output_dir=output_path.parent)
    try:
        raw = ScenarioReader().read(input_path)
        pipeline = CVRPPipeline(raw, cd, date, config=settings)
        solution = pipeline.solve()
    except (InputError, OSError) as exc:
        failure_path = ReportWriter.write_failure(str(exc), settings, cd, date or "")
        _publish_latest(failure_path, output_path)
        raise InputError(str(exc)) from exc
    assert pipeline.problem is not None
    path = ReportWriter.write(pipeline.problem, solution, settings)
    _publish_latest(path, output_path)
    inst.info("Artefatos publicados em %s", path)
    return {"status": solution.status, "directory": str(path)}


def _publish_latest(directory: Path, output_path: Path) -> None:
    """Compatibilidade: cópia atômica do envelope; conjunto completo fica no run."""
    with NamedTemporaryFile(dir=output_path.parent, prefix=".output-", delete=False) as temporary:
        temp_path = Path(temporary.name)
    try:
        shutil.copyfile(directory / "output.json", temp_path)
        temp_path.replace(output_path)
    finally:
        temp_path.unlink(missing_ok=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Resolve CVRP com CPLEX ou Docplex e publica JSON/Excel.")
    result.add_argument("path", type=Path, help="Diretório contendo input.json")
    result.add_argument("cd")
    result.add_argument("--date")
    result.add_argument("--backend", choices=("docplex", "cplex"), default="docplex")
    result.add_argument("--clusters", type=int, default=4, help="Use 1 para desabilitar a decomposição")
    result.add_argument("--parallel", action="store_true")
    result.add_argument("--workers", type=int, default=2)
    result.add_argument("--threads", type=int, default=1)
    result.add_argument("--cpu-budget", type=int, default=4)
    result.add_argument("--memory-budget-mb", type=int, default=4096)
    result.add_argument(
        "--time-limit", type=float, default=30, help="Orçamento de solve por split, compartilhado entre FOs"
    )
    result.add_argument("--total-seconds", type=float, help="Deadline cooperativo de computação; escrita usa reserva")
    result.add_argument("--mip-gap", type=float, default=0.01)
    result.add_argument("--abs-tol", type=float, default=1e-6)
    result.add_argument("--rel-tol", type=float, default=0)
    result.add_argument("--post-seconds", type=float, default=5)
    result.add_argument(
        "--distance-mode", choices=("complete_with_geography", "provided_only"), default="complete_with_geography"
    )
    result.add_argument("--seed", type=int, default=42)
    result.add_argument("--export-lp", action="store_true")
    result.add_argument("--cplex-log", action="store_true")
    return result


def main() -> None:
    arguments = parser()
    args = arguments.parse_args()
    try:
        settings = PipelineConfig(
            backend=args.backend,
            clusters=args.clusters,
            parallel=args.parallel,
            workers=args.workers,
            solver_threads=args.threads,
            cpu_budget=args.cpu_budget,
            memory_budget_mb=args.memory_budget_mb,
            solve_seconds=args.time_limit,
            total_seconds=args.total_seconds,
            mip_gap=args.mip_gap,
            absolute_tolerance=args.abs_tol,
            relative_tolerance=args.rel_tol,
            postprocess_seconds=args.post_seconds,
            distance_mode=args.distance_mode,
            seed=args.seed,
            export_lp=args.export_lp,
            cplex_log=args.cplex_log,
            output_dir=args.path,
        )
    except ValueError as exc:
        arguments.error(str(exc))
    inst.configure(args.path / "execution.log", force=True)
    try:
        result = run(args.path / "input.json", args.cd, args.date, args.path / "output.json", config=settings)
    except InputError as exc:
        arguments.exit(2, f"Entrada inválida: {exc}\n")
    if result["status"] not in {"feasible", "empty"}:
        arguments.exit(1, f"Execução terminou com status {result['status']}\n")


if __name__ == "__main__":
    main()
