"""Validação de entrada e fluxo real através dos dois backends."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from benchmark import create_input
from cvrp import CVRPPipeline, InstanceTransformer, PipelineConfig
from cvrp.domain.results import ModelSolution, Route, SplitResult
from cvrp.io.reader import InputError, ScenarioReader
from cvrp.report.routes import extract_routes
from cvrp.solve.executor import SplitExecutor
from cvrp.validation.solution import SolutionError, SolutionValidator, objective_vector


@pytest.mark.parametrize("backend", ["cplex", "docplex"])
@pytest.mark.parametrize("parallel", [False, True])
def test_complete_pipeline_has_exclusive_fleet_and_both_objectives(backend, parallel):
    raw = create_input(8, 4)
    settings = PipelineConfig(backend=backend, parallel=parallel, solve_seconds=2, postprocess_seconds=0)
    pipeline = CVRPPipeline(raw, "CD-BENCH", config=settings)
    solution = pipeline.solve()
    assert solution.status == "feasible"
    assert len(solution.splits) == 4
    assert len({r.vehicle_id for r in solution.routes}) == len(solution.routes)
    assert sum(len(r.customers) for r in solution.routes) == 8
    assert all(tuple(stage.objective for stage in split.stages) == ("cost", "balance") for split in solution.splits)
    assert all(split.stages[0].has_incumbent for split in solution.splits)
    SolutionValidator().validate(pipeline.problem, solution.routes)
    output = pipeline.run()
    assert output["instancia_resumo"]["clientes_atendidos"] == 8
    assert output["kpis_globais"]["custo_total"] == pytest.approx(
        objective_vector(pipeline.problem, pipeline.solution.routes)[0]
    )


@pytest.mark.parametrize("backend", ["docplex", "cplex"])
def test_single_problem_equivalent_cost_and_balance(backend):
    config = PipelineConfig(backend=backend, clusters=1, solve_seconds=2, postprocess_seconds=0, mip_gap=0)
    pipe = CVRPPipeline(create_input(3, 2), "CD-BENCH", config=config)
    result = pipe.solve()
    assert result.status == "feasible"
    assert result.splits[0].stages[0].proven_optimal
    assert result.splits[0].stages[1].proven_optimal
    assert len(result.routes) == 1
    assert result.splits[0].stages[1].balance == 0
    assert pipe.config == config


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantidade_caixas", -1),
        ("quantidade_caixas", 1.5),
        ("quantidade_caixas", True),
    ],
)
def test_invalid_discrete_demand(field, value):
    raw = create_input(1, 1)
    raw["pedidos"][0]["itens"][0][field] = value
    with pytest.raises(InputError):
        InstanceTransformer(raw, "CD-BENCH").prepare()


@pytest.mark.parametrize(
    "field,value",
    [
        ("capacidade_kg", 0),
        ("capacidade_m3", -1),
        ("capacidade_kg", float("nan")),
        ("custo_km_relativo", float("inf")),
        ("capacidade_m3", True),
    ],
)
def test_invalid_vehicle_numbers(field, value):
    raw = create_input(1, 1)
    raw["frota"]["tipos"][0][field] = value
    with pytest.raises(InputError):
        InstanceTransformer(raw, "CD-BENCH").prepare()


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda r: r.pop("metadata"), "metadata"),
        (lambda r: r["frota"]["disponibilidade"][0].update(em_manutencao=2), "manutenção"),
        (lambda r: r["clientes"][0].update(latitude=91), "coordenada"),
        (lambda r: r["metadata"].update(data_referencia="2026-02-30"), "Data"),
        (lambda r: r["catalogo_produtos"].append(r["catalogo_produtos"][0]), "duplicado"),
        (lambda r: r["frota"]["disponibilidade"][0].update(tipo="missing"), "não encontrado"),
    ],
)
def test_structural_and_business_errors(mutation, match):
    raw = create_input(1, 1)
    mutation(raw)
    with pytest.raises(InputError, match=match):
        InstanceTransformer(raw, "CD-BENCH").prepare()


def test_duplicates_identical_orders_and_fleet_aggregate_safely():
    raw = create_input(1, 1)
    raw["pedidos"].append(raw["pedidos"][0].copy())
    raw["frota"]["disponibilidade"].append(raw["frota"]["disponibilidade"][0].copy())
    problem = InstanceTransformer(raw, "CD-BENCH").prepare()
    assert problem.customers["C-00001"].demand_kg == 10
    assert len({v.identifier for v in problem.vehicles}) == 2
    raw["pedidos"][-1]["status"] = "CANCELADO"
    with pytest.raises(InputError, match="conflitante"):
        InstanceTransformer(raw, "CD-BENCH").prepare()


def test_joint_capacity_and_vehicle_eligibility(raw):
    raw["clientes"][1]["cd_atendimento"] = "CD"
    raw["frota"]["tipos"][0].update(capacidade_kg=100, capacidade_m3=1)
    raw["frota"]["tipos"][1].update(capacidade_kg=10, capacidade_m3=10)
    with pytest.raises(InputError, match="conjunta"):
        InstanceTransformer(raw, "CD").prepare()
    raw["frota"]["tipos"][1].update(capacidade_kg=100)
    with pytest.raises(InputError, match="ida e retorno"):
        InstanceTransformer(raw, "CD").prepare()


def test_provided_only_requires_outward_and_return_arcs():
    raw = create_input(1, 1)
    raw["distancias_conhecidas"] = [{"origem": "CD-BENCH", "destino": "C-00001", "distancia_km": 1}]
    with pytest.raises(InputError, match="ida e retorno"):
        InstanceTransformer(raw, "CD-BENCH", distance_mode="provided_only").prepare()
    raw["distancias_conhecidas"].append({"origem": "C-00001", "destino": "CD-BENCH", "distancia_km": 2})
    data = InstanceTransformer(raw, "CD-BENCH", distance_mode="provided_only").transform()
    assert data.distance[0, 1] == 1
    assert data.distance[1, 0] == 2


def test_empty_input_skips_solver_and_preprocessing(monkeypatch):
    raw = create_input(1, 1)
    raw["pedidos"] = []
    raw["frota"]["disponibilidade"] = []
    monkeypatch.setattr(SplitExecutor, "run", lambda *args: pytest.fail("solver called on empty input"))
    pipeline = CVRPPipeline(raw, "CD-BENCH")
    assert pipeline.solve().status == "empty"
    assert pipeline.run()["rotas"] == []


def test_partition_failure_retries_original_problem(monkeypatch):
    original = SplitExecutor.run
    calls = []

    def run(self, problem, splits, config, deadline=None, run_id=""):
        calls.append(len(splits))
        if len(splits) > 1:
            return tuple(
                SplitResult(
                    s.identifier,
                    (),
                    (),
                    "no_incumbent",
                    customer_ids=s.customer_ids,
                    vehicle_ids=tuple(v.identifier for v in s.vehicles),
                )
                for s in splits
            )
        return original(self, problem, splits, config, deadline, run_id)

    monkeypatch.setattr(SplitExecutor, "run", run)
    settings = PipelineConfig(solve_seconds=2, postprocess_seconds=0)
    result = CVRPPipeline(create_input(4, 4), "CD-BENCH", config=settings).solve()
    assert calls == [4, 1]
    assert result.status == "feasible"
    assert len(result.attempts) == 4
    assert any(d.code == "partition_fallback" for d in result.diagnostics)


def test_failed_global_fallback_keeps_partial_status(monkeypatch):
    def run(self, problem, splits, config, deadline=None, run_id=""):
        if len(splits) == 1:
            return (SplitResult(splits[0].identifier, (), (), "failed"),)
        first = splits[0]
        good = SplitResult(first.identifier, (Route(first.vehicles[0].identifier, first.customer_ids),), (), "feasible")
        return (good, *(SplitResult(s.identifier, (), (), "failed") for s in splits[1:]))

    monkeypatch.setattr(SplitExecutor, "run", run)
    result = CVRPPipeline(create_input(4, 4), "CD-BENCH").solve()
    assert result.status == "partial"
    assert len(result.routes) == 1
    assert result.postprocess is None
    assert result.attempts[0].status == "failed"


def test_memory_budget_and_deadline_return_honest_failure():
    settings = PipelineConfig(memory_budget_mb=1, postprocess_seconds=0)
    result = CVRPPipeline(create_input(1, 1), "CD-BENCH", config=settings).solve()
    assert result.status == "failed"
    assert any("memória" in d.message for d in result.diagnostics)
    timeout = replace(settings, memory_budget_mb=4096, total_seconds=1e-9)
    result = CVRPPipeline(create_input(1, 1), "CD-BENCH", config=timeout).solve()
    assert result.status == "no_incumbent"
    assert result.splits[0].status == "budget_exhausted"


def test_route_extraction_rejects_disconnected_cycle():
    data = InstanceTransformer(create_input(3, 1), "CD-BENCH").transform()
    chosen = ModelSolution(((0, 1, 0), (1, 0, 0), (2, 3, 0), (3, 2, 0)), 0, 0)
    with pytest.raises(SolutionError, match="desconectados"):
        extract_routes(data, chosen)


@pytest.mark.parametrize("backend", ["docplex", "cplex"])
def test_installed_cli_publishes_json_excel_lp_and_manifest(tmp_path, backend):
    scenario = tmp_path / backend
    scenario.mkdir()
    (scenario / "input.json").write_text(json.dumps(create_input(3, 2)))
    completed = subprocess.run(
        [
            str(Path(".venv/bin/cvrp").resolve()),
            str(scenario),
            "CD-BENCH",
            "--backend",
            backend,
            "--clusters",
            "1",
            "--time-limit",
            "2",
            "--post-seconds",
            "0",
            "--export-lp",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    output = json.loads((scenario / "output.json").read_text())
    final = next((scenario / "runs").iterdir())
    assert (final / "report.xlsx").is_file()
    assert json.loads((final / "manifest.json").read_text())["completed"]
    assert output == json.loads((final / "output.json").read_text())
    assert len(tuple(final.glob("solver/*/fo*.lp"))) == 2
    assert "lex_cost_limit" in next(final.glob("solver/*/fo2.lp")).read_text()


def test_cli_invalid_input_publishes_failure_with_exit_two(tmp_path):
    (tmp_path / "input.json").write_text("{}")
    completed = subprocess.run(
        [str(Path(".venv/bin/cvrp").resolve()), str(tmp_path), "CD"], capture_output=True, text=True
    )
    assert completed.returncode == 2
    output = json.loads((tmp_path / "output.json").read_text())
    assert output["status_solver"]["status"] == "invalid_input"
    assert output["rotas"] == []
    assert next((tmp_path / "runs").glob("*/report.xlsx")).is_file()


@pytest.mark.parametrize(
    "options",
    [
        {"clusters": 0},
        {"workers": True},
        {"solve_seconds": float("nan")},
        {"parallel": True, "workers": 3, "solver_threads": 2},
        {"export_lp": True},
        {"relative_tolerance": -1},
        {"seed": -1},
    ],
)
def test_invalid_pipeline_config(options):
    with pytest.raises(ValueError):
        PipelineConfig(**options)


def test_reader_reports_bad_json_and_unsupported_types(tmp_path):
    path = tmp_path / "input.json"
    path.write_text("{")
    with pytest.raises(InputError, match="JSON inválido"):
        ScenarioReader().read(path)
    with pytest.raises(InputError, match="objeto"):
        ScenarioReader().decode([])


def test_typed_input_obeys_same_domain_validation():
    typed = ScenarioReader().decode(create_input(1, 1))
    invalid = replace(typed, products=(replace(typed.products[0], weight_kg=-10),))
    with pytest.raises(InputError, match="peso"):
        InstanceTransformer(invalid, "CD-BENCH").prepare()
    invalid = replace(typed, availability=(replace(typed.availability[0], maintenance=2),))
    with pytest.raises(InputError, match="Manutenção"):
        InstanceTransformer(invalid, "CD-BENCH").prepare()


def test_huge_quantities_fail_as_input_error_instead_of_overflow():
    raw = create_input(1, 1)
    raw["pedidos"][0]["itens"][0]["quantidade_caixas"] = 10**400
    with pytest.raises(InputError, match="domínio"):
        InstanceTransformer(raw, "CD-BENCH").prepare()
    raw = create_input(1, 1)
    raw["parametros_operacionais"]["custo_por_km"] = 10**400
    with pytest.raises(InputError, match="representável"):
        InstanceTransformer(raw, "CD-BENCH").prepare()


def test_parallel_process_creation_failure_has_diagnostics_and_global_fallback(monkeypatch):
    def fail(**options):
        raise OSError("process creation failed")

    monkeypatch.setattr("cvrp.solve.executor.ProcessPoolExecutor", fail)
    config = PipelineConfig(parallel=True, solve_seconds=2, postprocess_seconds=0)
    result = CVRPPipeline(create_input(4, 4), "CD-BENCH", config=config).solve()
    assert result.status == "feasible"
    assert len(result.attempts) == 4
    assert all(attempt.status == "failed" for attempt in result.attempts)
    assert all("process creation failed" in attempt.diagnostics[0].message for attempt in result.attempts)


def test_explicit_empty_delivery_date_is_invalid():
    with pytest.raises(InputError, match="Data inválida"):
        InstanceTransformer(create_input(1, 1), "CD-BENCH", delivery_date="")
