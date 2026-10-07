"""Registros canônicos compartilhados pelos formatos JSON e Excel."""

from dataclasses import dataclass, fields
from typing import cast

type Cell = str | int | float | bool | None | tuple[str, ...]
type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class ReportRow:
    def record(self) -> dict[str, Cell]:
        return {field.name: cast(Cell, getattr(self, field.name)) for field in fields(self)}


@dataclass(frozen=True, slots=True)
class SummaryRow(ReportRow):
    id_execucao: str
    gerado_em: str
    hash_instancia: str
    versao_schema: str
    instancia: str
    moeda: str
    backend: str
    status: str
    clientes_elegiveis: int
    clientes_atendidos: int
    veiculos_disponiveis: int
    veiculos_utilizados: int
    demanda_total_kg: float
    demanda_total_m3: float
    capacidade_total_kg: float
    capacidade_total_m3: float
    custo_total: float
    custo_fixo: float
    custo_variavel: float
    distancia_total_km: float
    carga_total_kg: float
    carga_total_m3: float
    paradas_total: int
    equilibrio_paradas: float
    tempo_build_s: float
    tempo_solve_s: float
    num_variaveis: int
    num_restricoes: int
    num_nao_zeros: int
    configuracao: str
    tempos: str
    pos_processamento: str


@dataclass(frozen=True, slots=True)
class RouteRow(ReportRow):
    id_rota: int
    veiculo_id: str
    tipo_veiculo: str
    capacidade_kg: float
    capacidade_m3: float
    distancia_km: float
    carga_kg: float
    carga_m3: float
    custo_fixo: float
    custo_variavel: float
    custo_total: float
    ocupacao_kg_pct: float
    ocupacao_m3_pct: float
    num_paradas: int


@dataclass(frozen=True, slots=True)
class StopRow(ReportRow):
    id_rota: int
    veiculo_id: str
    seq: int
    no: str
    tipo: str
    razao_social: str
    demanda_kg: float
    demanda_m3: float
    pedidos: tuple[str, ...]
    distancia_arco_km: float
    distancia_acum_km: float
    custo_arco: float


@dataclass(frozen=True, slots=True)
class ObjectiveRow(ReportRow):
    split_id: str
    etapa: int
    objetivo: str
    status: str
    valor: float | None
    bound: float | None
    gap: float | None
    tempo_s: float
    tem_incumbente: bool
    otimo_comprovado: bool
    custo: float | None
    equilibrio: float | None
    limite_custo: float | None
    tentativa: str
    resultado_final: bool


@dataclass(frozen=True, slots=True)
class SplitRow(ReportRow):
    split_id: str
    status: str
    clientes: tuple[str, ...]
    veiculos: tuple[str, ...]
    clientes_atendidos: int
    rotas: int
    tempo_build_s: float
    num_variaveis: int
    num_restricoes: int
    num_nao_zeros: int
    limite_custo: float | None
    tentativa: str
    resultado_final: bool


@dataclass(frozen=True, slots=True)
class DiagnosticRow(ReportRow):
    codigo: str
    mensagem: str
    entidade: str
    split_id: str
    nivel: str


@dataclass(frozen=True, slots=True)
class ReportTable:
    name: str
    columns: tuple[str, ...]
    rows: tuple[ReportRow, ...]


@dataclass(frozen=True, slots=True)
class ReportData:
    resumo: tuple[SummaryRow, ...]
    rotas: tuple[RouteRow, ...]
    paradas: tuple[StopRow, ...]
    objetivos: tuple[ObjectiveRow, ...]
    splits: tuple[SplitRow, ...]
    diagnostico: tuple[DiagnosticRow, ...]

    def tables(self) -> tuple[ReportTable, ...]:
        definitions = (
            ("resumo", SummaryRow, self.resumo),
            ("rotas", RouteRow, self.rotas),
            ("paradas", StopRow, self.paradas),
            ("objetivos", ObjectiveRow, self.objetivos),
            ("splits", SplitRow, self.splits),
            ("diagnostico", DiagnosticRow, self.diagnostico),
        )
        return tuple(ReportTable(name, tuple(f.name for f in fields(kind)), rows) for name, kind, rows in definitions)
