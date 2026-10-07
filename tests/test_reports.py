"""Parité sémantique des six contenus publiés, y compris les cas sans solution."""

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from cvrp.config import PipelineConfig
from cvrp.domain.instance import Customer, Location, ProblemData, TravelData, Vehicle
from cvrp.domain.results import Diagnostic, Route, RoutingSolution, SplitResult, StageResult
from cvrp.io import writer
from cvrp.io.writer import ReportWriter
from cvrp.report import ReportProjector
from cvrp.report.canonical import instance_hash

XML = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def problem() -> ProblemData:
    depot = Location("CD", "Depósito", 0, 0)
    customers = {
        "C1": Customer(Location("C1", "=Cliente", 0, 0.01), 2, 1, ("P1", "P2")),
        "C2": Customer(Location("C2", "Segundo", 0, 0.02), 3, 1, ("P3",)),
    }
    locations = {"CD": depot, **{key: customer.location for key, customer in customers.items()}}
    travel = TravelData(locations, {("CD", "C1"): 2, ("C1", "CD"): 3, ("CD", "C2"): 4, ("C2", "CD"): 5}, {})
    return ProblemData(
        depot,
        "2026-10-07",
        customers,
        (Vehicle("V1", "VUC", 10, 10, 2), Vehicle("V2", "VUC", 10, 10, 3)),
        travel,
        10,
        "BRL",
    )


def solution(status: str = "feasible") -> RoutingSolution:
    routes = (
        (Route("V1", ("C1",)), Route("V2", ("C2",)))
        if status == "feasible"
        else (Route("V1", ("C1",)),)
        if status == "partial"
        else ()
    )
    stage = StageResult(
        "S1",
        "cost",
        "optimal" if routes else "time_limit",
        20 if routes else None,
        19 if routes else None,
        0.05 if routes else None,
        0.1,
        bool(routes),
        bool(routes),
        20 if routes else None,
        0 if routes else None,
    )
    split = SplitResult(
        "S1", routes, (stage,), status, cost_limit=20.000001, customer_ids=("C1", "C2"), vehicle_ids=("V1", "V2")
    )
    return RoutingSolution(routes, (split,), status, (Diagnostic("test", "Aviso", "C1"),), run_id="RUN-test")


def _column(reference: str) -> int:
    value = 0
    for character in reference:
        if character.isdigit():
            break
        value = value * 26 + ord(character) - ord("A") + 1
    return value - 1


def _cell(cell: ET.Element) -> object:
    kind = cell.attrib.get("t")
    if kind == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//s:t", XML))
    value = cell.findtext("s:v", namespaces=XML)
    if value is None:
        return None
    return value == "1" if kind == "b" else float(value)


def _xlsx_tables(path: Path) -> dict[str, list[dict[str, object]]]:
    tables: dict[str, list[dict[str, object]]] = {}
    with ZipFile(path) as workbook:
        sheets = ET.fromstring(workbook.read("xl/workbook.xml")).findall("s:sheets/s:sheet", XML)
        for index, sheet in enumerate(sheets, 1):
            xml = ET.fromstring(workbook.read(f"xl/worksheets/sheet{index}.xml"))
            xml_rows = xml.findall("s:sheetData/s:row", XML)
            headers = [str(_cell(cell)) for cell in xml_rows[0]]
            rows = []
            for xml_row in xml_rows[1:]:
                cells = {_column(cell.attrib["r"]): _cell(cell) for cell in xml_row}
                rows.append({name: cells.get(column) for column, name in enumerate(headers)})
            tables[sheet.attrib["name"]] = rows
    return tables


@pytest.mark.parametrize("status", ["feasible", "partial", "no_incumbent"])
def test_json_excel_parity_and_manifest(tmp_path: Path, status: str) -> None:
    directory = ReportWriter.write(problem(), solution(status), PipelineConfig(output_dir=tmp_path))
    tables = _xlsx_tables(directory / "report.xlsx")
    manifest = json.loads((directory / "manifest.json").read_text())
    for name, excel_rows in tables.items():
        records = json.loads((directory / f"{name}.json").read_text())
        assert manifest["counts"][name] == len(records) == len(excel_rows)
        for record, excel in zip(records, excel_rows, strict=True):
            assert record.keys() == excel.keys()
            for key, value in record.items():
                if isinstance(value, list):
                    assert json.loads(excel[key]) == value
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    assert excel[key] == pytest.approx(value)
                else:
                    assert excel[key] == value
    for file in manifest["files"]:
        data = (directory / file["path"]).read_bytes()
        assert len(data) == file["bytes"]
        assert sha256(data).hexdigest() == file["sha256"]
    output = json.loads((directory / "output.json").read_text())
    expected = 2 if status == "feasible" else 1 if status == "partial" else 0
    assert output["instancia_resumo"]["clientes_atendidos"] == expected
    assert output["kpis_globais"]["paradas_total"] == expected
    assert output["status_solver"]["status"] == status
    assert output["kpis_globais"]["custo_total"] == sum(r["kpis"]["custo_total"] for r in output["rotas"])
    with ZipFile(directory / "report.xlsx") as workbook:
        assert b"<f>" not in workbook.read("xl/worksheets/sheet3.xml")


def test_empty_contents_preserve_headers(tmp_path: Path) -> None:
    data = replace(problem(), customers={})
    directory = ReportWriter.write(data, RoutingSolution((), (), "empty"), PipelineConfig(output_dir=tmp_path))
    tables = _xlsx_tables(directory / "report.xlsx")
    assert (
        tables["rotas"] == tables["paradas"] == tables["objetivos"] == tables["splits"] == tables["diagnostico"] == []
    )
    manifest = json.loads((directory / "manifest.json").read_text())
    assert all(content["columns"] for content in manifest["tables"].values())
    assert manifest["run_id"].startswith("RUN-")
    assert "Z-" in manifest["run_id"]


def test_instance_hash_is_canonical_and_config_sensitive(tmp_path: Path) -> None:
    data = problem()
    reversed_data = replace(
        data,
        customers=dict(reversed(tuple(data.customers.items()))),
        vehicles=tuple(reversed(data.vehicles)),
        travel=replace(data.travel, overrides=dict(reversed(tuple(data.travel.overrides.items())))),
    )
    config = PipelineConfig()
    assert instance_hash(data, config) == instance_hash(reversed_data, config)
    assert instance_hash(data, config) == instance_hash(data, replace(config, output_dir=tmp_path, cplex_log=True))
    assert instance_hash(data, config) != instance_hash(data, replace(config, backend="cplex"))
    assert len(instance_hash(data, config)) == 71


def test_projector_reuses_identity_and_deduplicates_diagnostics() -> None:
    diagnostic = Diagnostic("warning", "Duplicado")
    data = replace(problem(), diagnostics=(diagnostic,))
    result = replace(solution(), diagnostics=(diagnostic,))
    projector = ReportProjector(data, result, PipelineConfig())
    assert projector.project() is projector.project()
    assert len(projector.project().diagnostico) == 1
    assert projector.output()["execucao"] == projector.output()["execucao"]


def test_failed_write_removes_staging_and_preserves_existing_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = PipelineConfig(output_dir=tmp_path)
    previous = ReportWriter.write(problem(), solution(), config)
    old_manifest = (previous / "manifest.json").read_bytes()

    def fail(*args: object) -> None:
        raise OSError("disk failure")

    monkeypatch.setattr(writer, "_write_workbook", fail)
    with pytest.raises(OSError, match="disk failure"):
        ReportWriter.write(problem(), replace(solution(), run_id="RUN-second"), config)
    assert list((tmp_path / "runs").iterdir()) == [previous]
    assert (previous / "manifest.json").read_bytes() == old_manifest


@pytest.mark.parametrize("limit", ["rows", "cell"])
def test_excel_limits_fail_without_partial_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: str
) -> None:
    config = PipelineConfig(output_dir=tmp_path)
    if limit == "rows":
        monkeypatch.setattr(writer, "EXCEL_ROWS", 2)
    else:
        monkeypatch.setattr(writer, "EXCEL_CELL_CHARACTERS", 5)
    with pytest.raises(ValueError, match="excede"):
        ReportWriter.write(problem(), solution(), config)
    assert not (tmp_path / "runs").exists()


def test_solver_artifacts_are_copied_and_checksummed(tmp_path: Path) -> None:
    artifact = tmp_path / "work" / "RUN-test" / "S1" / "model.lp"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("model")
    directory = ReportWriter.write(problem(), solution(), PipelineConfig(output_dir=tmp_path))
    manifest = json.loads((directory / "manifest.json").read_text())
    assert (directory / "solver" / "S1" / "model.lp").read_text() == "model"
    assert "solver/S1/model.lp" in {file["path"] for file in manifest["files"]}


def test_writer_requires_directory_and_unique_run(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="output_dir"):
        ReportWriter.write(problem(), solution(), PipelineConfig())
    config = PipelineConfig(output_dir=tmp_path)
    ReportWriter.write(problem(), solution(), config)
    with pytest.raises(FileExistsError, match="já publicada"):
        ReportWriter.write(problem(), solution(), config)


def test_invalid_input_report_has_no_fabricated_routes(tmp_path: Path) -> None:
    directory = ReportWriter.write_failure("Campo obrigatório ausente", PipelineConfig(output_dir=tmp_path), "CD")
    output = json.loads((directory / "output.json").read_text())
    assert output["status_solver"]["status"] == "invalid_input"
    assert output["rotas"] == output["splits"] == output["objetivos"] == []
    assert output["execucao"]["hash_instancia"] == ""
    assert output["diagnostico"][0]["codigo"] == "invalid_input"
    assert _xlsx_tables(directory / "report.xlsx")["rotas"] == []


def test_prior_attempts_are_separated_from_final_certificates() -> None:
    previous = replace(solution("no_incumbent").splits[0], split_id="S0")
    result = replace(solution(), attempts=(previous,))
    report = ReportProjector(problem(), result, PipelineConfig()).project()
    assert [row.tentativa for row in report.objetivos] == ["anterior", "final"]
    assert [row.resultado_final for row in report.splits] == [False, True]
    assert report.resumo[0].clientes_atendidos == 2


def test_summary_times_include_prior_attempts_but_model_size_describes_final() -> None:
    prior_stage = replace(solution().splits[0].stages[0], seconds=200)
    prior = replace(solution().splits[0], stages=(prior_stage,), build_seconds=100, variable_count=1000)
    final_stage = replace(solution().splits[0].stages[0], seconds=3)
    final = replace(solution().splits[0], stages=(final_stage,), build_seconds=2, variable_count=20)
    result = replace(solution(), splits=(final,), attempts=(prior,))
    summary = ReportProjector(problem(), result, PipelineConfig()).project().resumo[0]
    assert summary.tempo_build_s == 102
    assert summary.tempo_solve_s == 203
    assert summary.num_variaveis == 20
