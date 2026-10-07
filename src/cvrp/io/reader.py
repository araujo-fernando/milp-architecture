"""Decodificação tipada e validação estrutural na fronteira JSON."""

import json
from datetime import date
from math import isfinite
from pathlib import Path

from cvrp.domain.raw import (
    Availability,
    CirculationRule,
    DistanceOverride,
    Order,
    OrderItem,
    Place,
    Product,
    RawScenario,
    VehicleKind,
)


class InputError(ValueError):
    """Entrada inválida, com contexto de campo ou entidade."""


class Record:
    """Acesso por strings restrito à fronteira de desserialização."""

    def __init__(self, value: object, path: str = "input") -> None:
        if not isinstance(value, dict):
            raise InputError(f"{path}: esperado objeto JSON")
        self.values: dict[str, object] = value
        self.path = path

    def required(self, name: str) -> object:
        if name not in self.values:
            raise InputError(f"{self.path}.{name}: campo obrigatório")
        return self.values[name]

    def record(self, name: str) -> "Record":
        return Record(self.required(name), f"{self.path}.{name}")

    def rows(self, name: str, *, optional: bool = False) -> tuple["Record", ...]:
        values = self.values.get(name, []) if optional else self.required(name)
        if not isinstance(values, list):
            raise InputError(f"{self.path}.{name}: esperada lista")
        return tuple(Record(value, f"{self.path}.{name}[{i}]") for i, value in enumerate(values))

    def text(self, name: str) -> str:
        value = self.required(name)
        if not isinstance(value, str) or not value:
            raise InputError(f"{self.path}.{name}: esperada string não vazia")
        return value

    def boolean(self, name: str) -> bool:
        value = self.required(name)
        if not isinstance(value, bool):
            raise InputError(f"{self.path}.{name}: esperado booleano")
        return value

    def number(self, name: str, *, positive: bool = False) -> float:
        value = self.required(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputError(f"{self.path}.{name}: esperado número")
        try:
            number = float(value)
        except OverflowError as exc:
            raise InputError(f"{self.path}.{name}: número não representável") from exc
        if not isfinite(number) or number < 0 or (positive and number == 0):
            raise InputError(f"{self.path}.{name}: número fora do domínio")
        return number

    def integer(self, name: str) -> int:
        value = self.required(name)
        if type(value) is not int or value < 0:
            raise InputError(f"{self.path}.{name}: esperado inteiro não negativo")
        return value

    def coordinate(self, name: str, limit: float) -> float | None:
        value = self.required(name)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InputError(f"{self.path}.{name}: coordenada inválida")
        try:
            number = float(value)
        except OverflowError as exc:
            raise InputError(f"{self.path}.{name}: coordenada não representável") from exc
        if not isfinite(number) or not -limit <= number <= limit:
            raise InputError(f"{self.path}.{name}: coordenada fora dos limites")
        return number

    def texts(self, name: str) -> tuple[str, ...]:
        value = self.required(name)
        if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
            raise InputError(f"{self.path}.{name}: esperada lista de códigos")
        return tuple(value)

    def date(self, name: str) -> str:
        return valid_date(self.text(name))


def valid_date(value: str) -> str:
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"Data inválida: {value}") from exc
    return value


class ScenarioReader:
    def read(self, path: Path) -> RawScenario:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputError(f"JSON inválido: {exc}") from exc
        return self.decode(value)

    def decode(self, value: object) -> RawScenario:
        root = Record(value)
        parameters, fleet = root.record("parametros_operacionais"), root.record("frota")
        return RawScenario(
            reference_date=root.record("metadata").date("data_referencia"),
            currency=parameters.text("moeda"),
            cost_per_km=parameters.number("custo_por_km"),
            fixed_vehicle_cost=parameters.number("custo_fixo_por_veiculo"),
            depots=tuple(self._place(row, depot=True) for row in root.rows("centros_distribuicao")),
            clients=tuple(self._place(row, depot=False) for row in root.rows("clientes")),
            products=tuple(
                Product(
                    r.text("sku"), r.number("peso_kg_caixa", positive=True), r.number("volume_m3_caixa", positive=True)
                )
                for r in root.rows("catalogo_produtos")
            ),
            orders=tuple(self._order(row) for row in root.rows("pedidos")),
            vehicle_kinds=tuple(self._kind(row) for row in fleet.rows("tipos")),
            availability=tuple(self._availability(row) for row in fleet.rows("disponibilidade")),
            circulation=tuple(
                CirculationRule(r.text("cd"), r.text("tipo_veiculo"), r.texts("clientes_bloqueados"))
                for r in root.rows("restricoes_circulacao", optional=True)
            ),
            distances=tuple(
                DistanceOverride(r.text("origem"), r.text("destino"), r.number("distancia_km"))
                for r in root.rows("distancias_conhecidas", optional=True)
            ),
        )

    @staticmethod
    def _place(row: Record, *, depot: bool) -> Place:
        code = row.text("codigo")
        return Place(
            code,
            code if depot else row.text("razao_social"),
            code if depot else row.text("cd_atendimento"),
            row.boolean("ativo") if depot else True,
            row.coordinate("latitude", 90),
            row.coordinate("longitude", 180),
        )

    @staticmethod
    def _order(row: Record) -> Order:
        return Order(
            row.text("numero"),
            row.text("cliente"),
            row.text("status"),
            row.date("data_entrega"),
            tuple(OrderItem(r.text("sku"), r.integer("quantidade_caixas")) for r in row.rows("itens")),
        )

    @staticmethod
    def _kind(row: Record) -> VehicleKind:
        return VehicleKind(
            row.text("codigo"),
            row.number("capacidade_kg", positive=True),
            row.number("capacidade_m3", positive=True),
            row.number("custo_km_relativo", positive=True),
        )

    @staticmethod
    def _availability(row: Record) -> Availability:
        result = Availability(row.text("cd"), row.text("tipo"), row.integer("quantidade"), row.integer("em_manutencao"))
        if result.maintenance > result.quantity:
            raise InputError(f"{row.path}: manutenção excede frota")
        return result
