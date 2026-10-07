"""Publicação atômica de JSONs, Excel e manifesto por execução."""

import json
import shutil
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from typing import Protocol

import xlsxwriter

from cvrp.config import PipelineConfig
from cvrp.domain.instance import ProblemData
from cvrp.domain.results import Diagnostic, RoutingSolution
from cvrp.report import ReportData, ReportProjector
from cvrp.report.canonical import compact_json
from cvrp.report.data import Cell, ReportTable
from cvrp.report.projector import SCHEMA_VERSION

EXCEL_ROWS = 1_048_576
EXCEL_COLUMNS = 16_384
EXCEL_CELL_CHARACTERS = 32_767


class Worksheet(Protocol):
    def write_string(self, row: int, col: int, string: str) -> int: ...
    def write_number(self, row: int, col: int, number: float) -> int: ...
    def write_boolean(self, row: int, col: int, boolean: bool) -> int: ...


def excel_cell(value: Cell) -> str | int | float | bool | None:
    return compact_json(value) if isinstance(value, tuple) else value


def _check_table(table: ReportTable) -> None:
    if len(table.rows) + 1 > EXCEL_ROWS or len(table.columns) > EXCEL_COLUMNS:
        raise ValueError(f"Conteúdo {table.name} excede os limites de linhas/colunas do Excel")
    for row in table.rows:
        for value in row.record().values():
            cell = excel_cell(value)
            if isinstance(cell, str) and len(cell.encode("utf-16-le")) // 2 > EXCEL_CELL_CHARACTERS:
                raise ValueError(f"Conteúdo {table.name} excede {EXCEL_CELL_CHARACTERS} caracteres por célula")


def _write_cell(sheet: Worksheet, row: int, column: int, value: Cell) -> None:
    cell = excel_cell(value)
    if isinstance(cell, str):
        sheet.write_string(row, column, cell)
    elif isinstance(cell, bool):
        sheet.write_boolean(row, column, cell)
    elif isinstance(cell, (int, float)):
        sheet.write_number(row, column, cell)


def _write_json(path: Path, contents: object) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(contents, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _write_workbook(path: Path, report: ReportData) -> None:
    with xlsxwriter.Workbook(
        str(path), {"constant_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
    ) as workbook:
        for table in report.tables():
            sheet = workbook.add_worksheet(table.name)
            for column, name in enumerate(table.columns):
                sheet.write_string(0, column, name)
            for row_index, row in enumerate(table.rows, 1):
                record = row.record()
                for column, name in enumerate(table.columns):
                    _write_cell(sheet, row_index, column, record[name])


def _file_metadata(path: Path, staging: Path) -> dict[str, object]:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1_048_576), b""):
            digest.update(chunk)
    return {"path": path.relative_to(staging).as_posix(), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


class ReportWriter:
    @staticmethod
    def write(problem: ProblemData, solution: RoutingSolution, config: PipelineConfig) -> Path:
        return ReportWriter._write_projector(ReportProjector(problem, solution, config), config)

    @staticmethod
    def write_failure(message: str, config: PipelineConfig, depot_id: str = "", delivery_date: str = "") -> Path:
        solution = RoutingSolution((), (), "invalid_input", (Diagnostic("invalid_input", message, level="ERROR"),))
        projector = ReportProjector(None, solution, config, instance=f"{depot_id}/{delivery_date}")
        return ReportWriter._write_projector(projector, config)

    @staticmethod
    def _write_projector(projector: ReportProjector, config: PipelineConfig) -> Path:
        if config.output_dir is None:
            raise ValueError("ReportWriter requer config.output_dir")
        if Path(projector.run_id).name != projector.run_id or projector.run_id in {".", ".."}:
            raise ValueError("ID de execução deve ser um nome de diretório simples")
        report = projector.project()
        for table in report.tables():
            _check_table(table)
        runs = config.output_dir / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        destination = runs / projector.run_id
        if destination.exists():
            raise FileExistsError(f"Execução já publicada: {destination}")
        staging = Path(mkdtemp(prefix=f".{projector.run_id}-", dir=runs))
        try:
            ReportWriter._publish_files(staging, projector, report, config)
            staging.rename(destination)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return destination

    @staticmethod
    def _publish_files(staging: Path, projector: ReportProjector, report: ReportData, config: PipelineConfig) -> None:
        for table in report.tables():
            _write_json(staging / f"{table.name}.json", [row.record() for row in table.rows])
        _write_json(staging / "output.json", projector.output())
        _write_workbook(staging / "report.xlsx", report)
        work = config.output_dir / "work" / projector.run_id if config.output_dir else None
        if work is not None and work.is_dir():
            shutil.copytree(work, staging / "solver")
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_id": projector.run_id,
            "generated_at": projector.generated_at,
            "instance_hash": report.resumo[0].hash_instancia,
            "completed": True,
            "counts": {table.name: len(table.rows) for table in report.tables()},
            "tables": {
                table.name: {"json": f"{table.name}.json", "sheet": table.name, "columns": list(table.columns)}
                for table in report.tables()
            },
            "cell_encoding": {"tuple": "JSON array text", "null": "blank cell"},
            "files": [_file_metadata(path, staging) for path in sorted(staging.rglob("*")) if path.is_file()],
        }
        _write_json(staging / "manifest.json", manifest)
