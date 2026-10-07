"""Validação de identidade e referências do cenário operacional."""

from math import isfinite

from cvrp.domain.raw import Order, RawScenario
from cvrp.io.reader import InputError, valid_date


def _unique(values: tuple[str, ...], entity: str) -> None:
    if len(values) != len(set(values)):
        raise InputError(f"Código duplicado em {entity}")


class InputValidator:
    def validate(self, raw: RawScenario) -> None:
        self._domains(raw)
        _unique(tuple(p.code for p in raw.depots), "CDs")
        _unique(tuple(p.code for p in raw.clients), "clientes")
        _unique(tuple(p.sku for p in raw.products), "produtos")
        _unique(tuple(p.code for p in raw.vehicle_kinds), "tipos de frota")
        depots, clients = {p.code for p in raw.depots}, {p.code for p in raw.clients}
        if depots & clients:
            raise InputError("Códigos de clientes e CDs devem ser distintos")
        self._references(raw, depots, clients)
        self._orders(raw)
        self._distances(raw, depots | clients)

    @staticmethod
    def _domains(raw: RawScenario) -> None:
        """Também valida objetos construídos diretamente, sem passar pelo JSON."""
        valid_date(raw.reference_date)
        _number(raw.cost_per_km, "custo por km")
        _number(raw.fixed_vehicle_cost, "custo fixo")
        for product in raw.products:
            _number(product.weight_kg, f"peso {product.sku}", positive=True)
            _number(product.volume_m3, f"volume {product.sku}", positive=True)
        for vehicle in raw.vehicle_kinds:
            _number(vehicle.capacity_kg, f"capacidade kg {vehicle.code}", positive=True)
            _number(vehicle.capacity_m3, f"capacidade m³ {vehicle.code}", positive=True)
            _number(vehicle.relative_cost, f"custo relativo {vehicle.code}", positive=True)
        InputValidator._discrete_domains(raw)
        InputValidator._coordinates(raw)

    @staticmethod
    def _discrete_domains(raw: RawScenario) -> None:
        for available in raw.availability:
            _integer(available.quantity, "quantidade de veículos")
            _integer(available.maintenance, "veículos em manutenção")
            if available.maintenance > available.quantity:
                raise InputError("Manutenção excede quantidade de veículos")
        for order in raw.orders:
            valid_date(order.delivery_date)
            for item in order.items:
                _integer(item.boxes, f"caixas do pedido {order.number}")
        for arc in raw.distances:
            _number(arc.distance_km, "distância informada")

    @staticmethod
    def _coordinates(raw: RawScenario) -> None:
        for place in (*raw.depots, *raw.clients):
            _coordinate(place.latitude, 90, place.code)
            _coordinate(place.longitude, 180, place.code)

    @staticmethod
    def _references(raw: RawScenario, depots: set[str], clients: set[str]) -> None:
        kinds = {v.code for v in raw.vehicle_kinds}
        if any(c.depot_code not in depots for c in raw.clients):
            raise InputError("Cliente referencia CD não encontrado")
        if any(v.depot_code not in depots or v.kind not in kinds for v in raw.availability):
            raise InputError("Disponibilidade referencia CD/tipo não encontrado")
        for rule in raw.circulation:
            if rule.depot_code not in depots or rule.vehicle_kind not in kinds:
                raise InputError("Circulação referencia CD/tipo não encontrado")
            if not set(rule.customer_codes) <= clients:
                raise InputError("Circulação referencia cliente não encontrado")

    @staticmethod
    def _orders(raw: RawScenario) -> None:
        products = {p.sku for p in raw.products}
        seen: dict[str, Order] = {}
        for order in raw.orders:
            if order.number in seen and seen[order.number] != order:
                raise InputError(f"Pedido duplicado conflitante: {order.number}")
            seen[order.number] = order
            if any(item.sku not in products for item in order.items):
                raise InputError(f"SKU ausente no catálogo: pedido {order.number}")

    @staticmethod
    def _distances(raw: RawScenario, places: set[str]) -> None:
        seen: dict[tuple[str, str], float] = {}
        for arc in raw.distances:
            if arc.origin not in places or arc.destination not in places or arc.origin == arc.destination:
                raise InputError("Distância referencia arco inválido")
            key = (arc.origin, arc.destination)
            if key in seen and seen[key] != arc.distance_km:
                raise InputError(f"Distância duplicada conflitante: {key}")
            seen[key] = arc.distance_km


def _number(value: float, field: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{field}: esperado número")
    try:
        valid = isfinite(value) and value >= 0 and (not positive or value > 0)
    except OverflowError:
        valid = False
    if not valid:
        raise InputError(f"{field}: número fora do domínio")


def _integer(value: int, field: str) -> None:
    if type(value) is not int or value < 0:
        raise InputError(f"{field}: esperado inteiro não negativo")
    _number(value, field)


def _coordinate(value: float | None, limit: float, entity: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not -limit <= value <= limit:
        raise InputError(f"Coordenada inválida: {entity}")
    if not isfinite(value):
        raise InputError(f"Coordenada não finita: {entity}")
